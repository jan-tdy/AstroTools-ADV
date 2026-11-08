## What it does

Converts between the FWHM and the standard deviation of a Gaussian.

## How to use

1. Enter the **Value**, choose **Convert** (`FWHM -> sigma` or `sigma -> FWHM`) and press **Convert**.

## Reading the results

FWHM 1 gives sigma 0.424660900144. The constants are `gaussian_fwhm_to_sigma = 0.42466090014400953` and `gaussian_sigma_to_fwhm = 2.3548200450309493` (that is 2*sqrt(2 ln 2)).

## Tips and limits

- FWHM = 2.3548 sigma; for a pixel scale in arcseconds multiply the result by it.
