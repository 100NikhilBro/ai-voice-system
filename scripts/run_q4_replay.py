"""
Q4 Live Insights -- CLI Replay Runner
======================================
Replays one or more saved call transcripts at real-time speed
and reports nudges with full latency measurements and P50/P95 stats.

Usage:
  python scripts/run_q4_replay.py                           # replay all Q4 scenarios
  python scripts/run_q4_replay.py --name call_01_cooperative
  python scripts/run_q4_replay.py --speed 5.0               # 5x real-time speed
  python scripts/run_q4_replay.py --all-recordings           # replay all recordings including Q1/Q3

All replays process utterances one-by-one with inter-turn delays.
This is NOT post-call batch analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import io
import sys

# Force UTF-8 output on Windows to handle emoji and special chars
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.insights.replay_engine import TranscriptReplayEngine
from src.insights.nudge_engine import Nudge
from src.insights.latency_tracker import LatencyRecord

RECORDINGS_DIR = Path(__file__).parent.parent / "artifacts" / "recordings"
SCENARIOS_DIR  = Path(__file__).parent.parent / "artifacts" / "q4_scenarios"

LINE = "─" * 80
DLINE = "═" * 80


def _find_transcript(name: str) -> Path | None:
    for base_dir in [RECORDINGS_DIR, SCENARIOS_DIR]:
        candidate = base_dir / name / "transcript.json"
        if candidate.exists():
            return candidate
        # Q4 scenario files are flat json
        candidate_flat = SCENARIOS_DIR / name
        if candidate_flat.exists():
            return candidate_flat
        # result.json for Q3
        candidate2 = base_dir / name / "result.json"
        if candidate2.exists():
            return candidate2
    # Check if it's a plain filename in scenarios dir
    flat = SCENARIOS_DIR / name
    if flat.exists():
        return flat
    return None


async def replay_one(
    transcript_path: Path,
    speed: float = 3.0,
    confidence: float = 0.65,
    cooldown: float = 20.0,
) -> dict:
    """Replay a single transcript and return the summary."""
    print(f"\n{DLINE}")
    print(f"  REPLAYING: {transcript_path.name}  (speed={speed}x, confidence≥{confidence})")
    print(DLINE)

    engine = TranscriptReplayEngine(
        transcript_path=transcript_path,
        confidence_threshold=confidence,
        cooldown_seconds=cooldown,
        expiry_seconds=120.0,
        max_repetitions=3,
        replay_speed=speed,
    )
    engine.load()
    print(f"  Loaded {len(engine._turns)} turns")
    print()

    nudge_events: list[dict] = []
    current_turn = [0]

    def progress(i, total, speaker):
        current_turn[0] = i
        bar_width = 30
        filled = int(bar_width * i / max(total - 1, 1))
        bar = "█" * filled + "░" * (bar_width - filled)
        print(f"  [{bar}] Turn {i+1}/{total} [{speaker:8s}]", end="\r", flush=True)

    async def on_nudge(nudge: Nudge, rec: LatencyRecord):
        print()  # newline after progress bar
        print(f"  ┌─ 🔔 NUDGE @ Turn {rec.utterance_index}  [{nudge.priority}]")
        print(f"  │  Type    : {nudge.signal_type.value}")
        print(f"  │  Title   : {nudge.title}")
        print(f"  │  Action  : {nudge.action}")
        print(f"  │  Conf    : {nudge.confidence:.2f}")
        print(f"  │  Evidence: {nudge.evidence}")
        print(f"  │  T0→T4   : {rec.end_to_end_latency_ms:.1f}ms  "
              f"(ASR:{rec.asr_latency_ms:.1f}ms  "
              f"Detect:{rec.signal_detection_latency_ms:.1f}ms  "
              f"Gen:{rec.nudge_generation_latency_ms:.1f}ms  "
              f"Deliver:{rec.delivery_latency_ms:.1f}ms)")
        print(f"  └─ expires in {engine.nudge_engine.expiry_seconds:.0f}s")
        nudge_events.append({"nudge": nudge.to_dict(), "e2e_ms": rec.end_to_end_latency_ms})

    start = time.time()
    nudges = await engine.run(nudge_callback=on_nudge, progress_callback=progress)
    elapsed = time.time() - start

    print()  # clear progress bar line
    print()

    summary = engine.get_summary()
    stats = engine.latency_tracker.compute_stats()

    print(f"  {LINE}")
    print(f"  REPLAY COMPLETE in {elapsed:.2f}s")
    print(f"  {LINE}")
    print(f"  Turns processed      : {stats['session_turns']}")
    print(f"  Nudges generated     : {stats['turns_with_nudges']} turns / {len(nudges)} nudges")
    print()

    def _print_stat(label: str, s: dict):
        if s["count"] > 0:
            print(f"  {label:<32} P50={s['p50_ms']:6.1f}ms  P95={s['p95_ms']:6.1f}ms  "
                  f"mean={s['mean_ms']:6.1f}ms  max={s['max_ms']:6.1f}ms  (n={s['count']})")
        else:
            print(f"  {label:<32} (no data)")

    print(f"  ┌─ Latency Breakdown ──────────────────────────────────────────────────┐")
    _print_stat("ASR / Transcription (T1-T0)",     stats["asr_latency"])
    _print_stat("Signal Detection (T2-T1)",         stats["signal_detection"])
    _print_stat("Nudge Generation (T3-T2)",          stats["nudge_generation"])
    _print_stat("Delivery (T4-T3)",                  stats["delivery_latency"])
    _print_stat("End-to-End All Turns (T4-T0)",      stats["end_to_end_all_turns"])
    _print_stat("End-to-End Nudge Turns (T4-T0)",    stats["end_to_end_nudge_turns"])
    print(f"  └──────────────────────────────────────────────────────────────────────┘")

    summary["nudge_events"] = nudge_events
    return summary


def _get_default_scenarios() -> list[Path]:
    """Get all Q4 scenario files."""
    scenarios = sorted(SCENARIOS_DIR.glob("*.json"))
    return scenarios


def _get_all_transcripts() -> list[Path]:
    """Get all recording transcript.json files."""
    paths = []
    for folder in sorted(RECORDINGS_DIR.iterdir()):
        if folder.is_dir():
            t = folder / "transcript.json"
            if t.exists():
                paths.append(t)
    return paths


async def main():
    parser = argparse.ArgumentParser(description="Q4 Live Insights Replay Runner")
    parser.add_argument("--name", help="Specific transcript name to replay")
    parser.add_argument("--speed", type=float, default=5.0,
                        help="Replay speed multiplier (default: 5.0 = 5x real-time)")
    parser.add_argument("--confidence", type=float, default=0.65,
                        help="Minimum signal confidence threshold (default: 0.65)")
    parser.add_argument("--cooldown", type=float, default=5.0,
                        help="Nudge cooldown seconds (default: 5.0 for demo)")
    parser.add_argument("--all-recordings", action="store_true",
                        help="Replay all saved call recordings (Q1/Q3)")
    parser.add_argument("--output", help="Save JSON report to this path")
    args = parser.parse_args()

    print(f"\n{DLINE}")
    print(f"  Q4 LIVE INSIGHTS — REPLAY RUNNER")
    print(f"  Real-time speed replay: utterances processed one-by-one with delays")
    print(f"  NOT post-call batch analysis")
    print(DLINE)

    if args.name:
        # Single named scenario
        path = _find_transcript(args.name)
        if not path:
            print(f"ERROR: Transcript '{args.name}' not found.")
            print(f"  Q4 scenarios: {[p.stem for p in _get_default_scenarios()]}")
            print(f"  Q1/Q3 recordings: {[p.parent.name for p in _get_all_transcripts()]}")
            sys.exit(1)
        results = [await replay_one(path, args.speed, args.confidence, args.cooldown)]
    elif args.all_recordings:
        paths = _get_all_transcripts()
        results = []
        for p in paths:
            r = await replay_one(p, args.speed, args.confidence, args.cooldown)
            results.append(r)
    else:
        # Default: replay all Q4 scenarios
        paths = _get_default_scenarios()
        if not paths:
            print("No Q4 scenario files found in artifacts/q4_scenarios/")
            sys.exit(1)
        results = []
        for p in paths:
            r = await replay_one(p, args.speed, args.confidence, args.cooldown)
            results.append(r)

    # Aggregate report
    print(f"\n{DLINE}")
    print(f"  AGGREGATE REPORT ACROSS ALL REPLAYED CALLS")
    print(DLINE)

    total_turns = sum(r["latency_stats"]["session_turns"] for r in results)
    total_nudges = sum(r["nudge_stats"]["total_nudges_generated"] for r in results)

    print(f"  Total turns processed: {total_turns}")
    print(f"  Total nudges generated: {total_nudges}")
    print()

    # Collect all end-to-end latencies
    all_e2e: list[float] = []
    for r in results:
        for rec_dict in r.get("latency_records", []):
            e2e = rec_dict.get("end_to_end_latency_ms", 0)
            if e2e > 0:
                all_e2e.append(e2e)

    if all_e2e:
        all_e2e.sort()

        def pct(data, p):
            idx = (p / 100) * (len(data) - 1)
            lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
            return data[lo] + (idx - lo) * (data[hi] - data[lo])

        print(f"  End-to-End Latency (T0→T4) across all turns:")
        print(f"    P50 = {pct(all_e2e, 50):.1f}ms")
        print(f"    P95 = {pct(all_e2e, 95):.1f}ms")
        print(f"    max = {max(all_e2e):.1f}ms")
        print(f"    n   = {len(all_e2e)}")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"\n  Report saved to: {out_path}")

    print()
    print(DLINE)
    print(f"  ✅ Q4 REPLAY COMPLETE")
    print(DLINE)


if __name__ == "__main__":
    asyncio.run(main())
