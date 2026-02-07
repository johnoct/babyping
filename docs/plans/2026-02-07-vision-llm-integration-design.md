# Vision LLM Integration Design

## Problem

BabyPing's motion detection is pixel-based — it knows *something moved* but not *what happened*. A blanket shifting and a baby climbing the crib railing trigger the same alert. Parents get woken up for nothing, or worse, learn to ignore alerts. We need semantic scene understanding: "baby is face-down", "baby is standing in crib", "baby is not visible".

## Solution

Add an optional `VisionAnalyzer` background thread that sends motion-triggered frames to a local vision LLM (via Ollama HTTP API) and returns structured safety assessments. The vision layer is **motion-gated** — it only runs when the existing pixel-diff detector fires, so 95%+ of frames never touch the LLM. Zero impact on the main capture loop.

### Why Ollama?

| Option | Speed | Setup | Cross-Platform | Verdict |
|---|---|---|---|---|
| **Ollama** | Good | `brew install ollama && ollama pull moondream` | Mac, Linux, Windows | **Winner** — zero Python deps, HTTP API, model management built in |
| mlx-vlm | Fastest on Mac (21-87% faster) | `pip install mlx-vlm`, Mac only | Apple Silicon only | Future optimization — add as optional backend later |
| llama.cpp server | Good | Manual build + GGUF download | All | More setup friction, same HTTP API pattern |
| vLLM | Best on NVIDIA | Docker + CUDA | Linux (GPU) | Overkill for consumer hardware |

Ollama wins because: (1) one-command install, (2) handles model downloading/quantization/serving, (3) OpenAI-compatible HTTP API, (4) no Python ML dependencies added to BabyPing, (5) cross-platform. Power users can swap in mlx-vlm or llama.cpp server since we talk HTTP.

### Why Moondream 2B?

| Model | Params | RAM | Latency (M1) | Strengths |
|---|---|---|---|---|
| SmolVLM2-256M | 256M | ~1 GB | ~1-2s | Ultra-light, RPi viable |
| **Moondream 2B** | 1.86B | ~2.5 GB | **~2-4s** | **Best edge detection, gaze tracking, structured JSON, purpose-built for monitoring** |
| Gemma 3 4B | 4.3B | ~4 GB | ~3-5s | Best descriptions, strong llama.cpp support |
| Qwen2.5-VL-7B | 7B | ~6 GB | ~4-7s | Max accuracy, used by ai-baby-monitor |

Moondream is the sweet spot: fast enough for near-real-time (2-4s per frame on base M1), small enough for 8GB Macs, and purpose-built for detection/grounding tasks. The `--vision-model` flag lets users pick any Ollama-supported vision model.

## Architecture

```
Main Loop (10fps)
  │
  ├─ Motion detected? ──YES──► VisionAnalyzer._queue (maxsize=1)
  │                                     │
  │                                     ▼
  │                            VisionAnalyzer._run() [daemon thread]
  │                              1. Encode frame → JPEG → base64
  │                              2. POST to Ollama /api/chat
  │                              3. Parse structured JSON response
  │                              4. If unsafe → alert + event log
  │                                     │
  │                                     ▼
  │                            FrameBuffer (vision_result, vision_time)
  │                            EventLog ("vision" event)
  │                            send_notification() if unsafe
  │
  └─ No motion ──► skip vision (saves ~95% of inference)
```

### Why Motion-Gated?

- A 2B model at 2-4s/frame can process ~15-30 frames/minute — plenty for safety monitoring
- Without gating, we'd burn 100% GPU on empty crib frames
- Motion detection is essentially free (CPU, <1ms) — perfect cheap pre-filter
- The ai-baby-monitor project confirms this pattern works in production

### Thread Model

Mirrors `AudioMonitor` exactly:

```python
class VisionAnalyzer:
    def __init__(self, model, ollama_url, rules, cooldown, event_log, frame_buffer):
        self._queue = queue.Queue(maxsize=1)  # Only latest frame matters
        self._lock = threading.Lock()
        self._last_result = None
        self._last_analysis_time = None
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def is_alive(self):
        return self._running and self._thread is not None and self._thread.is_alive()

    def enqueue_frame(self, frame):
        """Non-blocking. Drops old frame if queue full (we only want the latest)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            pass

    def get_last_result(self):
        with self._lock:
            return self._last_result

    def get_last_analysis_time(self):
        with self._lock:
            return self._last_analysis_time
```

### Ollama HTTP Integration

```python
def _analyze_frame(self, frame):
    """Send frame to Ollama, return parsed result dict."""
    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    image_b64 = base64.b64encode(jpeg.tobytes()).decode('utf-8')

    payload = {
        "model": self._model,
        "messages": [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self._user_prompt, "images": [image_b64]}
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 100,
        }
    }

    resp = requests.post(
        f"{self._ollama_url}/api/chat",
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return json.loads(content)
```

Key choices:
- **`stream: false`** — for short responses (~50-100 tokens), non-streaming is faster (no SSE overhead)
- **`temperature: 0.1`** — near-deterministic for safety judgments
- **`num_predict: 100`** — cap output tokens to bound latency
- **`format: "json"`** — Ollama's constrained decoding ensures valid JSON
- **`timeout: 30`** — generous timeout for cold model loads; steady-state is 2-5s
- **JPEG quality 85** — good enough for VLM understanding, smaller payload than PNG

### Prompt Engineering

**System prompt:**
```
You are a baby safety monitor. Analyze the camera frame and evaluate safety rules.
Respond with JSON only. Be conservative — only alert on clear, unambiguous safety concerns.
Do not alert on normal movements like shifting, stretching, or turning to the side.
```

**User prompt (constructed from rules):**
```
Evaluate this baby monitor frame against these safety rules:
1. Baby should not be face-down on the mattress
2. Baby should not be climbing or standing in the crib
3. Baby should be visible in the frame

Respond with this exact JSON format:
{"safe": true/false, "reason": "brief explanation or null", "baby_visible": true/false, "position": "on back/on side/on stomach/sitting/standing/unknown"}
```

**Default rules (shipped with BabyPing):**
1. Baby should not be face-down on the mattress
2. Baby should not be climbing or standing in the crib
3. Baby should be visible in the frame

Users override with `--vision-rules`:
```bash
babyping --vision-model moondream \
  --vision-rules "Baby should not be uncovered" \
                 "No pets should be in the crib"
```

### Structured Output Schema

```json
{
  "safe": true,
  "reason": null,
  "baby_visible": true,
  "position": "on back"
}
```

```json
{
  "safe": false,
  "reason": "Baby appears to be face-down on the mattress",
  "baby_visible": true,
  "position": "on stomach"
}
```

Fields:
- `safe` (bool) — primary alert trigger
- `reason` (string|null) — human-readable explanation, shown in notification and event log
- `baby_visible` (bool) — whether a baby is detected in frame
- `position` (string) — baby's position: "on back", "on side", "on stomach", "sitting", "standing", "unknown"

### Hallucination Mitigation

Vision LLMs hallucinate. For a baby monitor, a false "unsafe" alert at 3 AM is bad. Strategies:

1. **Consecutive confirmation** — require N consecutive "unsafe" results before alerting (default: 2). A single hallucinated frame won't trigger a notification.
2. **Low temperature (0.1)** — reduces creative/random outputs
3. **Conservative system prompt** — explicitly instructs "only alert on clear, unambiguous concerns"
4. **Cooldown integration** — vision alerts respect the same `--cooldown` as motion alerts
5. **Confidence via repetition** — if the model says unsafe twice in a row on fresh frames, it's likely real

```python
# In _run() loop:
if not result["safe"]:
    self._consecutive_unsafe += 1
    if self._consecutive_unsafe >= self._confirm_count:
        self._fire_alert(result)
        self._consecutive_unsafe = 0
else:
    self._consecutive_unsafe = 0
```

### Event Log Integration

Add `"vision"` to `VALID_EVENT_TYPES` in `events.py`:

```python
VALID_EVENT_TYPES = ("motion", "sound", "vision")
```

Vision events include:
```python
event_log.log_event(
    "vision",
    reason=result["reason"],
    position=result.get("position"),
    baby_visible=result.get("baby_visible"),
    snapshot=snap_filename,
)
```

### FrameBuffer Changes

Add vision state to `FrameBuffer` (same pattern as audio):

```python
# New fields in __init__:
self._vision_enabled = False
self._vision_result = None
self._last_vision_time = None
self._vision_alerts_enabled = True

# New getters/setters (same lock pattern as audio):
set_vision_enabled / get_vision_enabled
set_vision_result / get_vision_result
set_last_vision_time / get_last_vision_time
set_vision_alerts_enabled / get_vision_alerts_enabled
```

### Web UI Changes

**Status endpoint** (`/status`) — add:
```json
{
  "vision_enabled": true,
  "vision_result": {"safe": true, "position": "on back", "baby_visible": true},
  "last_vision_time": 1707300000.0,
  "vision_alerts_enabled": true
}
```

**UI elements:**
- Vision status card in the status bar (next to motion card): shows last result, position, baby_visible
- Vision alert toggle (same pattern as motion/sound toggles)
- Vision events in the bottom sheet event log (new "vision" type with reason text)
- Amber glow animation on vision alert (distinct from red motion glow)

**Alerts endpoint** (`POST /alerts`) — add `vision_alerts` toggle.

### CLI Arguments

```python
# Vision LLM (new argument group)
parser.add_argument("--vision-model", default=None,
                    help="Ollama vision model name (e.g., moondream). Enables AI scene analysis.")
parser.add_argument("--ollama-url", default="http://localhost:11434",
                    help="Ollama API URL (default: http://localhost:11434)")
parser.add_argument("--vision-rules", nargs="+", default=None,
                    help="Safety rules for vision analysis (default: built-in rules)")
parser.add_argument("--vision-interval", type=float, default=0.0,
                    help="Minimum seconds between vision analyses, 0=analyze every motion (default: 0)")
parser.add_argument("--vision-confirm", type=int, default=2,
                    help="Consecutive unsafe frames required before alerting (default: 2)")
```

### Main Loop Integration

In `main()`, after audio monitor setup (~line 500):

```python
# Vision LLM
vision_analyzer = None
if args.vision_model:
    from vision import VisionAnalyzer
    vision_analyzer = VisionAnalyzer(
        model=args.vision_model,
        ollama_url=args.ollama_url,
        rules=args.vision_rules,
        cooldown=args.cooldown,
        confirm_count=args.vision_confirm,
        interval=args.vision_interval,
        event_log=event_log,
        frame_buffer=frame_buffer,
    )
    vision_analyzer.start()
    frame_buffer.set_vision_enabled(True)
    print(f"  Vision:       {args.vision_model} via {args.ollama_url}")
```

In the motion detection block (~line 584), after motion is confirmed:

```python
if motion and vision_analyzer is not None:
    vision_analyzer.enqueue_frame(display_frame)
```

Health check (same pattern as audio, ~line 609):

```python
if vision_analyzer is not None and not vision_analyzer.is_alive():
    print("Warning: Vision analyzer stopped — disabling vision")
    send_notification("BabyPing", "Vision analyzer disconnected")
    frame_buffer.set_vision_enabled(False)
    vision_analyzer = None
```

Sync vision state to frame buffer (same pattern as audio, ~line 623):

```python
if vision_analyzer is not None:
    result = vision_analyzer.get_last_result()
    if result is not None:
        frame_buffer.set_vision_result(result)
    analysis_time = vision_analyzer.get_last_analysis_time()
    if analysis_time is not None:
        frame_buffer.set_last_vision_time(analysis_time)
```

Cleanup in `finally` block (~line 652):

```python
if vision_analyzer is not None:
    vision_analyzer.stop()
```

## Graceful Degradation

- **Ollama not running** — VisionAnalyzer logs warning, retries with backoff, doesn't crash BabyPing
- **Model not found** — clear error message: "Model 'moondream' not found. Run: ollama pull moondream"
- **Slow inference** — queue drops old frames, only latest frame analyzed
- **Malformed JSON** — parse error logged, frame skipped, no alert
- **Network timeout** — 30s timeout, logged, frame skipped
- **Thread dies** — health check in main loop disables vision (same as audio pattern)

## Performance Budget

| Metric | Without Vision | With Vision |
|---|---|---|
| Main loop FPS | 10 | **10 (unchanged)** |
| CPU overhead | baseline | +~5% (queue + base64 encoding) |
| RAM (BabyPing process) | ~50 MB | ~55 MB (Ollama manages model memory separately) |
| RAM (Ollama process) | N/A | ~2.5 GB (Moondream 2B Q4) |
| Vision throughput | N/A | ~1 frame every 2-5s (motion-gated) |
| Alert latency | instant (motion) | +2-4s (semantic) + confirm window |

## Files Changed

- `vision.py` (new): `VisionAnalyzer` class — background thread, Ollama HTTP client, prompt construction, result parsing, alert firing
- `babyping.py`: CLI args, VisionAnalyzer instantiation, motion-gated frame enqueue, health check, frame buffer sync, cleanup
- `events.py`: Add `"vision"` to `VALID_EVENT_TYPES`, add `reason`/`position`/`baby_visible` to `log_event` kwargs
- `web.py`: `/status` vision fields, `/alerts` vision toggle, vision status card UI, vision events in bottom sheet, amber glow
- `tests/test_vision.py` (new): Unit tests for VisionAnalyzer (queue, thread lifecycle, Ollama mocking, JSON parsing, confirmation logic)
- `tests/test_babyping.py`: New --vision-* arg parsing tests
- `tests/test_events.py`: Vision event type tests
- `tests/test_web.py`: Vision status/alerts endpoint tests
- `requirements.txt`: Add `requests>=2.31` (only new dependency — for Ollama HTTP calls)

## Future Optimizations

1. **mlx-vlm backend** — optional in-process MLX inference for 21-87% speed boost on Apple Silicon
2. **Multi-frame analysis** — send 2-3 frames spanning 5-10s for temporal reasoning ("baby was sitting, now standing")
3. **Fine-tuned model** — fine-tune Moondream on baby safety dataset for higher accuracy
4. **Cry detection model** — specialized audio classifier alongside the vision LLM
5. **OpenAI-compatible API** — support any OpenAI-compatible endpoint (LM Studio, vLLM, llama.cpp server) via `--ollama-url`
