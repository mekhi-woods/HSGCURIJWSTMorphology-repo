import os
import math
import datetime
import numpy as np
from astropy.modeling.models import Gaussian2D
from photutils.datasets import make_noise_image

def dms_to_degrees(dms_string):     # FOR USE ON DECLINATION AND LATITUDE
    degrees, minutes, seconds = map(float, dms_string.split(':'))
    degrees += minutes / 60 + seconds / 3600
    return degrees

def time_to_degrees(time_string):   # FOR USE ON RIGHT ASCENSION AND HOUR ANGLE
    hours, minutes, seconds = map(float, time_string.split(':'))
    total_seconds = hours * 3600 + minutes * 60 + seconds
    degrees = total_seconds / 240
    return degrees

def degrees_to_time(degree_string):   # FOR USE ON RIGHT ASCENSION AND HOUR ANGLE
    totalSecs = float(degree_string) * 240
    time = str(datetime.timedelta(seconds=totalSecs))
    return time

def degrees_to_dms(degreeStr):     # FOR USE ON DECLINATION AND LATITUDE
    degrees, decimals = map(int, degreeStr.split('.'))
    decimals = str(decimals * 60)
    minutes = decimals[0:2]
    seconds = str(int(decimals[2:]) * 60)
    return f'{degrees}:{minutes}:{seconds[0:2]}.{seconds[2:]}'

def stringSeparator(str, interval=2, separator=':'):
    return separator.join([str[i:i + interval] for i in range(0, len(str), interval)])

# Shifts an individual wavelength based on a given value for z
def blueshifter(z, wavelength):  # in microns!!!
    restWL = wavelength / (z + 1)
    return restWL

# Shifts a list of wavelengths based on a given value for z
def listBlueshifter(z, wavelengths):  # in microns!!!
    restList = []
    for WL in wavelengths:
        restWL = WL / (z + 1)
        restList.append(restWL)
    return restList

# Avoids hidden folders/files when iterating through a directory
def listdir_nohidden(path):
    for f in os.listdir(path):
        if not f.startswith('.'):
            yield f

# Rotates a point n radians about another point
def rotate(origin, point, angle):
    ox, oy = origin
    px, py = point

    qx = ox + math.cos(angle) * (px - ox) - math.sin(angle) * (py - oy)
    qy = oy + math.sin(angle) * (px - ox) + math.cos(angle) * (py - oy)
    return qx, qy

def gusRotate(origin, point, angle):
    ox, oy = origin
    px, py = point
    hyp = math.sqrt((px - ox)**2 + (py - oy)**2)

    qx = ox - (hyp * math.cos(angle))
    qy = oy - (hyp * math.sin(angle))
    return qx, qy

def centerPoint(array, point):
    (x, y) = point
    (height, width) = array.shape

    if (height - y) >= (height / 2):
        # crop above and below y at (height - y - 1)
        newArr = array[0:(2*y) - 1, :]
    else:
        # crop above and below y at (height - y)
        newArr = array[y - (height - y):2*(y - (height - y)) - 1, :]

    if (width - x) > (width / 2) or (width - x) == (width / 2):
        # crop left and right of x at (width - x - 1)
        newArr = newArr[:, 0:(2*x) - 1]
    else:
        # crop left and right of x at (width - x)
        newArr = newArr[:, x - (width - x):2*(x - (width - x)) - 1]

    return newArr

def errorSum(array):
    lastLine = 0
    for line in array:
        print(line)
        lastVal = 0
        for val in line:
            lastVal = np.sqrt(lastVal**2 + val**2)
        lastLine = np.sqrt(lastLine**2 + lastVal**2)

    return lastLine

# Theta in degrees
def mockGalaxy(xSD, ySD, theta, nx, ny):
    g = Gaussian2D(100.0, nx/2, ny/2, xSD, ySD, theta=theta * np.pi / 180.0)
    y, x = np.mgrid[0:ny, 0:nx]
    noise = make_noise_image((ny, nx), distribution='gaussian', mean=0.0,
                             stddev=2.0, seed=1234)
    data = g(x, y) + noise

    return data
