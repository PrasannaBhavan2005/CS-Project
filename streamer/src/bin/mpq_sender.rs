//! Frame sender (QUIC client, the lecturer's device). Connects from the first
//! local address, adds one path per further local address, waits --warmup-ms
//! for path validation, then releases frame i of the (rotated) clip at its
//! capture time on a new unidirectional stream: a 16-byte part header
//! {frame_id, 0, size, size} and the frame's bytes, written with fin. Streams
//! are non-incremental at one urgency, so TQUIC sends them in stream-id order
//! (oldest frame first). Exits when the receiver closes the connection.
//!
//! Output (--out): seq,frame_id,frame_type,size_bytes,stream_id,capture_ts_us,send_start_us
//! (--paths-log): ts_us,local,srtt_us,min_rtt_us,rttvar_us,cwnd,sent_bytes,acked_bytes,lost_bytes,pacing_rate,in_slow_start

use std::cell::RefCell;
use std::collections::HashMap;
use std::error::Error;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::net::{IpAddr, SocketAddr};
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use bytes::Bytes;
use clap::Parser;
use log::{error, info, warn, LevelFilter};
use tquic::{
    CongestionControlAlgorithm, Config, Connection, Endpoint, MultipathAlgorithm, PacketInfo,
    TlsConfig, TransportHandler,
};
use tquic_tools::QuicSocket;

use streamer::*;

#[derive(Parser)]
#[clap(about = "Send a workload frame trace over multipath TQUIC, one stream per frame")]
struct Opt {
    #[clap(long)]
    connect: SocketAddr,
    /// One QUIC path per address; the first one carries the handshake.
    #[clap(long, value_delimiter = ',', required = true)]
    local_addresses: Vec<IpAddr>,
    #[clap(long)]
    enable_multipath: bool,
    #[clap(long, default_value = "minrtt")]
    multipath_algor: MultipathAlgorithm,
    #[clap(long, default_value = "cubic")]
    cc: CongestionControlAlgorithm,
    /// Workload trace (csv: frame_id,frame_type,size_bytes,pts_ms).
    #[clap(long)]
    frames: PathBuf,
    /// Start the clip at this frame and wrap around (paired runs share it).
    #[clap(long, default_value_t = 0)]
    clip_offset: usize,
    /// Delay between handshake and the first frame, so extra paths are validated.
    #[clap(long, default_value_t = 1000)]
    warmup_ms: u64,
    /// Give up this long after the first frame.
    #[clap(long, default_value_t = 120)]
    max_duration_s: u64,
    /// Per-frame send log (csv).
    #[clap(long)]
    out: PathBuf,
    /// Per-STREAM-frame path log from TQUIC's team7 hook (csv).
    #[clap(long)]
    frame_path_log: Option<PathBuf>,
    /// Per-path stats every 100 ms (csv).
    #[clap(long)]
    paths_log: Option<PathBuf>,
    #[clap(long)]
    log_file: PathBuf,
    #[clap(long, default_value = "info")]
    log_level: LevelFilter,
    #[clap(long)]
    qlog_dir: Option<PathBuf>,
}

#[derive(Default)]
struct State {
    conn: Option<u64>,
    established: Option<Instant>,
    closed: bool,
    extra_paths: Vec<SocketAddr>,
    remote: Option<SocketAddr>,
    /// Unwritten tail of a frame whose write was cut short (fin goes with it).
    pending: HashMap<u64, Bytes>,
    qlog_dir: Option<PathBuf>,
}

struct Handler {
    st: Rc<RefCell<State>>,
}

impl TransportHandler for Handler {
    fn on_conn_created(&mut self, conn: &mut Connection) {
        if let Some(dir) = &self.st.borrow().qlog_dir {
            let id = conn.trace_id().to_string();
            match File::create(dir.join(format!("{id}.qlog"))) {
                Ok(f) => conn.set_qlog(Box::new(f), "mpq_sender".into(), id),
                Err(e) => warn!("qlog: {e}"),
            }
        }
    }

    fn on_conn_established(&mut self, conn: &mut Connection) {
        let mut st = self.st.borrow_mut();
        st.conn = conn.index();
        st.established = Some(Instant::now());
        info!("{} established", conn.trace_id());
        let remote = st.remote.unwrap();
        for local in st.extra_paths.clone() {
            match conn.add_path(local, remote) {
                Ok(_) => info!("added path {local} -> {remote}"),
                Err(e) => error!("add_path {local}: {e:?}"),
            }
        }
    }

    fn on_conn_closed(&mut self, conn: &mut Connection) {
        info!("{} closed", conn.trace_id());
        self.st.borrow_mut().closed = true;
    }

    fn on_stream_created(&mut self, _conn: &mut Connection, _stream_id: u64) {}

    fn on_stream_readable(&mut self, _conn: &mut Connection, _stream_id: u64) {}

    fn on_stream_writable(&mut self, conn: &mut Connection, stream_id: u64) {
        let mut st = self.st.borrow_mut();
        let Some(tail) = st.pending.remove(&stream_id) else {
            let _ = conn.stream_want_write(stream_id, false);
            return;
        };
        match conn.stream_write(stream_id, tail.clone(), true) {
            Ok(n) if n < tail.len() => {
                st.pending.insert(stream_id, tail.slice(n..));
            }
            Ok(_) => {
                let _ = conn.stream_want_write(stream_id, false);
            }
            Err(e) => warn!("stream {stream_id} write: {e:?}"),
        }
    }

    fn on_stream_closed(&mut self, _conn: &mut Connection, _stream_id: u64) {}

    fn on_new_token(&mut self, _conn: &mut Connection, _token: Vec<u8>) {}
}

fn log_paths(conn: &mut Connection, w: &mut BufWriter<File>) -> std::io::Result<()> {
    let ts = now_us();
    let tuples: Vec<_> = conn.paths_iter().collect();
    for t in tuples {
        if let Ok(s) = conn.get_path_stats(t.local, t.remote) {
            writeln!(
                w,
                "{ts},{},{},{},{},{},{},{},{},{},{}",
                t.local, s.srtt, s.min_rtt, s.rttvar, s.final_cwnd, s.sent_bytes, s.acked_bytes,
                s.lost_bytes, s.pacing_rate, s.in_slow_start as u8
            )?;
        }
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let opt = Opt::parse();
    let mut routes = Vec::new();
    if let Some(p) = &opt.frame_path_log {
        routes.push(Route::csv(FRAME_PATH_TARGET, p, "ts_us,stream_id,path_id,offset,len,fin,local"));
    }
    SplitLogger::install(opt.log_level, &opt.log_file, routes)?;
    let frames = rotate(&load_frames(&opt.frames)?, opt.clip_offset);

    let mut config = Config::new()?;
    config.set_max_idle_timeout(60_000);
    config.set_initial_max_data(64 << 20);
    config.set_initial_max_stream_data_uni(8 << 20);
    config.set_initial_max_streams_uni(1 << 20);
    config.set_congestion_control_algorithm(opt.cc);
    config.enable_multipath(opt.enable_multipath);
    config.set_multipath_algorithm(opt.multipath_algor);
    config.set_active_connection_id_limit(4);
    let mut tls = TlsConfig::new_client_config(vec![ALPN.to_vec()], false)?;
    tls.set_verify(false);
    config.set_tls_config(tls);

    let mut poll = mio::Poll::new()?;
    let mut sock = QuicSocket::new(&SocketAddr::new(opt.local_addresses[0], 0), poll.registry())?;
    let mut extra_paths = Vec::new();
    if opt.enable_multipath {
        for ip in &opt.local_addresses[1..] {
            extra_paths.push(sock.add(&SocketAddr::new(*ip, 0), poll.registry())?);
        }
    }
    let sock = Rc::new(sock);
    let st = Rc::new(RefCell::new(State {
        extra_paths,
        remote: Some(opt.connect),
        qlog_dir: opt.qlog_dir.clone(),
        ..Default::default()
    }));
    let mut endpoint = Endpoint::new(Box::new(config), false, Box::new(Handler { st: st.clone() }), sock.clone());
    endpoint.connect(sock.local_addr(), opt.connect, Some("example.org"), None, None, None)?;
    info!("connecting {} -> {}", sock.local_addr(), opt.connect);

    let term = Arc::new(AtomicBool::new(false));
    signal_hook::flag::register(signal_hook::consts::SIGTERM, term.clone())?;
    signal_hook::flag::register(signal_hook::consts::SIGINT, term.clone())?;

    let mut out = BufWriter::new(File::create(&opt.out)?);
    writeln!(out, "seq,frame_id,frame_type,size_bytes,stream_id,capture_ts_us,send_start_us")?;
    let mut paths_log = match &opt.paths_log {
        Some(p) => {
            let mut w = BufWriter::new(File::create(p)?);
            writeln!(w, "ts_us,local,srtt_us,min_rtt_us,rttvar_us,cwnd,sent_bytes,acked_bytes,lost_bytes,pacing_rate,in_slow_start")?;
            Some(w)
        }
        None => None,
    };
    let warmup = Duration::from_millis(opt.warmup_ms);
    let mut next = 0;
    let mut start: Option<(Instant, u64)> = None; // (instant, monotonic us)
    let mut next_paths_log = Instant::now();
    let mut buf = vec![0u8; 65536];
    let mut events = mio::Events::with_capacity(1024);

    loop {
        let (conn_idx, established) = {
            let st = st.borrow();
            (st.conn, st.established)
        };
        let mut wait = None;
        if let (Some(idx), Some(est)) = (conn_idx, established) {
            if start.is_none() && Instant::now() >= est + warmup {
                start = Some((Instant::now(), now_us()));
                let n_paths = endpoint.conn_get_mut(idx).map_or(0, |c| c.paths_iter().count());
                info!("streaming {} frames from offset {} over {n_paths} path(s)", frames.len(), opt.clip_offset);
            }
            match start {
                Some((t0, m0)) => {
                    // Write every frame that is due.
                    while next < frames.len() && Instant::now() >= t0 + Duration::from_micros(frames[next].1) {
                        let (f, t_rel) = &frames[next];
                        let Some(conn) = endpoint.conn_get_mut(idx) else { break };
                        let sid = conn.stream_uni_new(0, false)?;
                        let mut data = vec![0u8; HEADER_LEN + f.size];
                        let h = PartHeader { frame_id: f.id, offset: 0, length: f.size as u32, frame_size: f.size as u32 };
                        data[..HEADER_LEN].copy_from_slice(&h.encode());
                        let data = Bytes::from(data);
                        let ts = now_us();
                        let n = conn.stream_write(sid, data.clone(), true)?;
                        if n < data.len() {
                            st.borrow_mut().pending.insert(sid, data.slice(n..));
                            conn.stream_want_write(sid, true)?;
                        }
                        writeln!(out, "{next},{},{},{},{sid},{},{ts}", f.id, f.typ, f.size, m0 + t_rel)?;
                        next += 1;
                    }
                    if next < frames.len() {
                        wait = Some((t0 + Duration::from_micros(frames[next].1)).saturating_duration_since(Instant::now()));
                    } else if t0.elapsed() > Duration::from_secs(opt.max_duration_s) {
                        warn!("giving up after {} s", opt.max_duration_s);
                        break;
                    }
                }
                None => wait = Some((est + warmup).saturating_duration_since(Instant::now())),
            }
            if let Some(w) = paths_log.as_mut() {
                if Instant::now() >= next_paths_log {
                    if let Some(conn) = endpoint.conn_get_mut(idx) {
                        log_paths(conn, w)?;
                    }
                    next_paths_log += Duration::from_millis(100);
                }
                let d = next_paths_log.saturating_duration_since(Instant::now());
                wait = Some(wait.map_or(d, |x| x.min(d)));
            }
        }

        endpoint.process_connections()?;
        if term.load(Ordering::Relaxed) || st.borrow().closed {
            break;
        }

        let timeout = match (endpoint.timeout(), wait) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        };
        if let Err(e) = poll.poll(&mut events, timeout) {
            if e.kind() != std::io::ErrorKind::Interrupted {
                return Err(e.into());
            }
        }
        for ev in events.iter().filter(|e| e.is_readable()) {
            loop {
                match sock.recv_from(&mut buf, ev.token()) {
                    Ok((len, local, remote)) => {
                        let info = PacketInfo { src: remote, dst: local, time: Instant::now() };
                        if let Err(e) = endpoint.recv(&mut buf[..len], &info) {
                            error!("recv: {e:?}");
                        }
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                    Err(e) => return Err(e.into()),
                }
            }
        }
        endpoint.on_timeout(Instant::now());
    }

    info!("sent {next} of {} frames", frames.len());
    out.flush()?;
    if let Some(w) = paths_log.as_mut() {
        w.flush()?;
    }
    log::logger().flush();
    Ok(())
}
