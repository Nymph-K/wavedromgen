# Example diagrams

Open these with:

```bash
python main.py examples/demo.json
python main.py examples/ddr_read.json
```

- `demo.json` — a six-lane UART-style frame with a bus, data labels, head/foot
  text and tick marks.
- `ddr_read.json` — the DDR read transaction from the WaveDrom tutorial,
  exercising `period`, `phase`, buses and data labels.

All characters follow the WaveDrom wave syntax:
<https://wavedrom.com/tutorial.html>.
