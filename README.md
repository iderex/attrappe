# attrappe

SCPI over VISA is a cleanly defined interface and driver libraries exist, but nothing on the other side answers physically plausibly with noise, thermal drift, warm-up time, range overflow, quantisation, occasional timeouts and firmware quirks. Rudimentary dummy instruments do exist in PyMeasure and QCoDeS and this board says so; the difference is the failure modes that measurement software actually breaks on, which nobody tests systematically. Done when a real driver talks to it unmodified and cannot tell the difference, and a deliberately fragile piece of measurement code fails against it the way it would fail against the instrument.

Planning happens on the issue tracker first. Every decision that shapes
the architecture is written down there with its reasons before the code
that depends on it exists.

See [NOTICE.md](NOTICE.md) for the intended-use notice.
