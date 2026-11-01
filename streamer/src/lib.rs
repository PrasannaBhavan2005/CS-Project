//! Shared pieces of the frame sender and receiver.
//!
//! The sender (QUIC client, the lecturer's device) sends every video frame,
//! or every part of a split frame, on its own unidirectional QUIC stream to
//! the receiver (QUIC server). Each stream starts with a 16-byte part header
//! {frame_id, offset, length, frame_size} followed by `length` bytes of
//! payload; the receiver completes a frame when the union of the byte ranges
//! received from any streams covers [0, frame_size).

use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;
use std::sync::Mutex;

use log::{Level, LevelFilter, Metadata, Record};

pub const ALPN: &[u8] = b"mpq-video";
pub const HEADER_LEN: usize = 16;
/// Log target of the per-path accounting hook in TQUIC (team7 branch).
pub const FRAME_PATH_TARGET: &str = "tquic::frame_path";

/// CLOCK_MONOTONIC in microseconds. Sender and receiver run on the same host
/// (two network namespaces, one kernel clock), so their timestamps compare
/// directly. Not the wall clock: WSL2 steps it by about half a second every
/// half minute or so, which shows up as fake frame lateness.
pub fn now_us() -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: valid pointer to a timespec; CLOCK_MONOTONIC always exists on Linux.
    unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    ts.tv_sec as u64 * 1_000_000 + ts.tv_nsec as u64 / 1000
}

#[derive(Clone, Debug, PartialEq)]
pub struct Frame {
    pub id: u32,
    pub typ: char,
    pub size: usize,
    pub pts_us: u64,
}

/// Read a workload trace (csv: frame_id,frame_type,size_bytes,pts_ms).
pub fn load_frames(path: &Path) -> std::io::Result<Vec<Frame>> {
    parse_frames(&std::fs::read_to_string(path)?)
}

pub fn parse_frames(text: &str) -> std::io::Result<Vec<Frame>> {
    let mut frames = Vec::new();
    for line in text.lines().skip(1).filter(|l| !l.is_empty()) {
        let f: Vec<&str> = line.split(',').collect();
        let bad = || std::io::Error::new(std::io::ErrorKind::InvalidData, line.to_string());
        if f.len() < 4 {
            return Err(bad());
        }
        frames.push(Frame {
            id: f[0].parse().map_err(|_| bad())?,
            typ: f[1].chars().next().ok_or_else(bad)?,
            size: f[2].parse().map_err(|_| bad())?,
            pts_us: (f[3].parse::<f64>().map_err(|_| bad())? * 1000.0).round() as u64,
        });
    }
    Ok(frames)
}

/// The clip played from frame `offset`, wrapping around once, with capture
/// times (us from the start of sending) on one continuous timeline: the
/// frames before `offset` follow the last frame one frame interval later.
pub fn rotate(frames: &[Frame], offset: usize) -> Vec<(Frame, u64)> {
    let n = frames.len();
    if n == 0 {
        return Vec::new();
    }
    let interval = if n > 1 { (frames[n - 1].pts_us - frames[0].pts_us) / (n as u64 - 1) } else { 0 };
    let span = frames[n - 1].pts_us - frames[0].pts_us + interval;
    let base = frames[offset % n].pts_us;
    (0..n)
        .map(|i| {
            let k = (offset + i) % n;
            let t = if k >= offset % n { frames[k].pts_us - base } else { frames[k].pts_us + span - base };
            (frames[k].clone(), t)
        })
        .collect()
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PartHeader {
    pub frame_id: u32,
    pub offset: u32,
    pub length: u32,
    pub frame_size: u32,
}

impl PartHeader {
    pub fn encode(&self) -> [u8; HEADER_LEN] {
        let mut h = [0u8; HEADER_LEN];
        h[0..4].copy_from_slice(&self.frame_id.to_be_bytes());
        h[4..8].copy_from_slice(&self.offset.to_be_bytes());
        h[8..12].copy_from_slice(&self.length.to_be_bytes());
        h[12..16].copy_from_slice(&self.frame_size.to_be_bytes());
        h
    }

    pub fn decode(h: &[u8]) -> PartHeader {
        let u = |i: usize| u32::from_be_bytes(h[i..i + 4].try_into().unwrap());
        PartHeader { frame_id: u(0), offset: u(4), length: u(8), frame_size: u(12) }
    }
}

/// Byte ranges of one frame received so far (sorted, disjoint, half-open).
#[derive(Clone, Debug, Default)]
pub struct Coverage {
    ranges: Vec<(u32, u32)>,
}

impl Coverage {
    /// Add [start, end); overlapping or adjacent ranges are merged.
    pub fn add(&mut self, start: u32, end: u32) {
        if start >= end {
            return;
        }
        let (mut s, mut e) = (start, end);
        let mut out = Vec::with_capacity(self.ranges.len() + 1);
        for &(a, b) in &self.ranges {
            if b < s || a > e {
                out.push((a, b));
            } else {
                s = s.min(a);
                e = e.max(b);
            }
        }
        out.push((s, e));
        out.sort_unstable();
        self.ranges = out;
    }

    /// True when [0, size) is covered.
    pub fn complete(&self, size: u32) -> bool {
        size == 0 || self.ranges.first().is_some_and(|&(a, b)| a == 0 && b >= size)
    }

    pub fn covered_bytes(&self) -> u64 {
        self.ranges.iter().map(|&(a, b)| (b - a) as u64).sum()
    }
}

/// Where records of one TQUIC log target go: their own file, each line
/// prefixed with the monotonic time ("<ts_us><sep><message>").
pub struct Route {
    pub target: &'static str,
    pub path: std::path::PathBuf,
    /// First line of the file, if any (a csv header).
    pub header: Option<&'static str>,
    pub sep: char,
}

impl Route {
    pub fn csv(target: &'static str, path: &Path, header: &'static str) -> Route {
        Route { target, path: path.to_path_buf(), header: Some(header), sep: ',' }
    }
}

/// Logger that writes ordinary log records to one file and the records of
/// each routed target (per-frame path bytes) to their own files, so analysis
/// needs no log parsing.
pub struct SplitLogger {
    level: LevelFilter,
    main: Mutex<BufWriter<File>>,
    routes: Vec<(&'static str, char, Mutex<BufWriter<File>>)>,
}

impl SplitLogger {
    pub fn install(level: LevelFilter, main: &Path, routes: Vec<Route>) -> std::io::Result<()> {
        let mut open = Vec::new();
        for r in routes {
            let mut w = BufWriter::new(File::create(&r.path)?);
            if let Some(h) = r.header {
                writeln!(w, "{h}")?;
            }
            open.push((r.target, r.sep, Mutex::new(w)));
        }
        let max = if open.is_empty() { level } else { level.max(LevelFilter::Debug) };
        let logger = SplitLogger { level, main: Mutex::new(BufWriter::new(File::create(main)?)), routes: open };
        log::set_boxed_logger(Box::new(logger)).expect("logger already set");
        log::set_max_level(max);
        Ok(())
    }

    fn route(&self, target: &str) -> Option<&(&'static str, char, Mutex<BufWriter<File>>)> {
        self.routes.iter().find(|(t, _, _)| *t == target)
    }
}

impl log::Log for SplitLogger {
    fn enabled(&self, m: &Metadata) -> bool {
        if self.route(m.target()).is_some() {
            return m.level() <= Level::Debug;
        }
        // Routed-only targets stay out of the main log.
        if m.target() == FRAME_PATH_TARGET {
            return false;
        }
        m.level() <= self.level
    }

    fn log(&self, r: &Record) {
        if !self.enabled(r.metadata()) {
            return;
        }
        match self.route(r.target()) {
            Some((_, sep, w)) => {
                let _ = writeln!(w.lock().unwrap(), "{}{}{}", now_us(), sep, r.args());
            }
            None => {
                let _ = writeln!(self.main.lock().unwrap(), "{} {} {}: {}", now_us(), r.level(), r.target(), r.args());
            }
        }
    }

    fn flush(&self) {
        let _ = self.main.lock().unwrap().flush();
        for (_, _, w) in &self.routes {
            let _ = w.lock().unwrap().flush();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn header_roundtrip() {
        let h = PartHeader { frame_id: 7, offset: 1000, length: 2345, frame_size: 55_000 };
        assert_eq!(PartHeader::decode(&h.encode()), h);
    }

    #[test]
    fn coverage_whole_frame_in_one_part() {
        let mut c = Coverage::default();
        assert!(!c.complete(100));
        c.add(0, 100);
        assert!(c.complete(100));
    }

    #[test]
    fn coverage_split_parts_any_order() {
        // Two parts of a 100-byte frame, second part first.
        let mut c = Coverage::default();
        c.add(60, 100);
        assert!(!c.complete(100));
        c.add(0, 60);
        assert!(c.complete(100));
        assert_eq!(c.covered_bytes(), 100);
    }

    #[test]
    fn coverage_gap_and_rescue_overlap() {
        // Parts [0,40) and [70,100) arrived; the rescue resends [30,80) on the
        // other path, overlapping both: complete, 100 distinct bytes.
        let mut c = Coverage::default();
        c.add(0, 40);
        c.add(70, 100);
        assert!(!c.complete(100));
        assert_eq!(c.covered_bytes(), 70);
        c.add(30, 80);
        assert!(c.complete(100));
        assert_eq!(c.covered_bytes(), 100);
    }

    #[test]
    fn coverage_duplicate_and_adjacent() {
        let mut c = Coverage::default();
        c.add(0, 50);
        c.add(0, 50); // duplicate (redundant scheduler, rescue)
        c.add(50, 99); // adjacent, one byte short
        assert!(!c.complete(100));
        assert_eq!(c.covered_bytes(), 99);
        c.add(99, 100);
        assert!(c.complete(100));
    }

    #[test]
    fn parse_and_rotate() {
        let text = "frame_id,frame_type,size_bytes,pts_ms\n0,I,500,0\n1,P,100,40\n2,P,120,80\n3,P,90,120\n";
        let f = parse_frames(text).unwrap();
        assert_eq!(f.len(), 4);
        assert_eq!(f[2], Frame { id: 2, typ: 'P', size: 120, pts_us: 80_000 });
        let r = rotate(&f, 2);
        let got: Vec<(u32, u64)> = r.iter().map(|(fr, t)| (fr.id, *t)).collect();
        // Frames 2, 3, then 0, 1 one interval after frame 3.
        assert_eq!(got, vec![(2, 0), (3, 40_000), (0, 80_000), (1, 120_000)]);
        let r0 = rotate(&f, 0);
        assert_eq!(r0.iter().map(|(_, t)| *t).collect::<Vec<_>>(), vec![0, 40_000, 80_000, 120_000]);
    }
}
