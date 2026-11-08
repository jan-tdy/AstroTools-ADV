## What it does

Builds convolution kernels (Gaussian, box, top-hat, custom) and combines them by addition, subtraction, convolution or scaling.

## How to use

1. Choose the **Kernel** class: `Gaussian1DKernel`, `Gaussian2DKernel`, `Box1DKernel`, `Box2DKernel`, `Tophat2DKernel` and others in the list.
2. **Parameters** is a `key=value` list (default `x_stddev=2, y_stddev=2, theta=0`). Model kernels take a model expression.
3. **x_size** / **y_size** must be odd; `0` picks the size automatically (8 sigma).
4. **Discretization** (`center`, `linear_interp`, `oversample`, `integrate`) with **Oversample factor**. **Normalize**: `as built`, `integral` or `peak`.
5. Press **Build kernel**. It is stored under **Store as** (default `kernel`).
6. **Kernel arithmetic (A op B)**: choose **Kernel A**, **Kernel B**, **Arithmetic** (`add`, `subtract`, `convolve`, `scale` with **Scalar**) and press the button.

## Reading the results

Default Gaussian: `shape (17, 17)`, `sum 1`, `min / max 4.47779e-09 / 0.0397901`, `center [8, 8]`, `separable True`. The **Preview** tab shows the kernel as an image.

## Tips and limits

- The automatic size is 17 pixels for sigma 2, but cuts off at 8 sigma; a smaller **x_size** truncates the wings and the kernel stops summing exactly to 1 unless normalised.
- Use the stored kernel in [Convolve image](convolve.md) by choosing `workspace kernel`.
