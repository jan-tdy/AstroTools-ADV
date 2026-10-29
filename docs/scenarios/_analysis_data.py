"""Seeded sample data shared by the Analysis scenarios (typed into expression fields)."""

# A Gaussian line (amplitude 3, centre 0.7, sigma 1.2) on a 0.5 continuum, noise sigma 0.1.
GAUSS_X = "np.linspace(-5, 5, 101)"
GAUSS_Y = ("3*np.exp(-0.5*((np.linspace(-5, 5, 101) - 0.7)/1.2)**2) + 0.5"
           " + np.random.default_rng(42).normal(0, 0.1, 101)")

# The same line with four cosmic-ray-like spikes of +2 on every 25th sample starting at index 3.
GAUSS_Y_SPIKES = GAUSS_Y + " + np.where(np.arange(101) % 25 == 3, 2.0, 0.0)"

# 200 values from N(100, 5) plus three gross outliers.
CLIP_DATA = "np.concatenate([np.random.default_rng(3).normal(100, 5, 200), [160, 175, 40]])"

# Two overlapping populations: N(0, 1) x 400 and N(4, 0.5) x 150.
BIMODAL = ("np.concatenate([np.random.default_rng(7).normal(0, 1, 400),"
           " np.random.default_rng(8).normal(4, 0.5, 150)])")
