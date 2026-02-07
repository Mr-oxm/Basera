"""Channel Mixer non-destructive adjustment."""

import numpy as np

from .adjustment_base import Adjustment


class ChannelMixer(Adjustment):
    """Mix colour channels using a 3x3 matrix.

    Each output channel is a linear combination of the three input
    channels.  Default is the identity matrix (no change).

    All values are in percentages; 100 % means the channel passes
    through unchanged, 0 % means no contribution.  Negative values
    subtract.

    Parameters
    ----------
    red_red, red_green, red_blue : float
        How much R, G, B contribute to the **output Red** channel.
    green_red, green_green, green_blue : float
        How much R, G, B contribute to the **output Green** channel.
    blue_red, blue_green, blue_blue : float
        How much R, G, B contribute to the **output Blue** channel.
    """

    def __init__(self) -> None:
        super().__init__(
            "Channel Mixer",
            {
                "red_red": 100, "red_green": 0, "red_blue": 0,
                "green_red": 0, "green_green": 100, "green_blue": 0,
                "blue_red": 0, "blue_green": 0, "blue_blue": 100,
            },
        )

    def apply(self, image: np.ndarray, params: dict) -> np.ndarray:
        rgb = self._rgb(image)
        alpha = self._alpha(image)

        # Build 3x3 matrix (row = output channel, col = input channel)
        matrix = np.array([
            [
                float(params.get("red_red", 100)),
                float(params.get("red_green", 0)),
                float(params.get("red_blue", 0)),
            ],
            [
                float(params.get("green_red", 0)),
                float(params.get("green_green", 100)),
                float(params.get("green_blue", 0)),
            ],
            [
                float(params.get("blue_red", 0)),
                float(params.get("blue_green", 0)),
                float(params.get("blue_blue", 100)),
            ],
        ], dtype=np.float32) / 100.0  # percentages → fractions

        # Vectorised matrix multiply: (H, W, 3) @ (3, 3)^T → (H, W, 3)
        result = np.einsum("...c,oc->...o", rgb, matrix)

        return self._merge(result, alpha)
