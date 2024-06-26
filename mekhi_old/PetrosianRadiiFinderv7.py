"""
Created by Mekhi D. Woods
04/03/2024
Current Version: 1.0

"""
import os
import time
import numpy as np
import matplotlib.pyplot as plt

from scipy.integrate import simpson

from astroquery.mast import Observations

import astropy.units as u
from astropy.io import fits
from astropy.visualization import ZScaleInterval
from astropy.convolution import convolve
from astropy.visualization import simple_norm
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
# from gwcs import WCS

from photutils.segmentation import make_2dgaussian_kernel, detect_sources, deblend_sources, SourceCatalog
from photutils.isophote import Ellipse, EllipseGeometry
from photutils.aperture import EllipticalAperture
from photutils.background import Background2D, MedianBackground

from astropy.utils.data import get_pkg_data_filename
from astropy.wcs.utils import skycoord_to_pixel

SYS_TIME = str(int(time.time())) # System Time, for purposes of naming files uniquely
PIX_SCALE = 0.031 # arcsec/pix, from https://jwst-docs.stsci.edu/jwst-near-infrared-camera
SPEED_OF_LIGHT = 3e5 # km/s
H0 = 73.8 #km/s/Mpc
DISPLAY_MODE = False

class petrosianObject():
    def __init__(self, ID='None', z=None, pos=(0, 0), SB=[], SBerr=[], iso_radii=[], iso_eps=[], isolist=None, aper=None, petroR=0.00):
        self.ID = ID
        self.z = z
        self.pos = pos
        self.SB = SB
        self.SBerr = SBerr
        self.iso_radii = iso_radii
        self.iso_eps = iso_eps
        self.isolist = isolist
        self.aper = aper
        self.petroR = petroR
        return

    def __str__(self):
        return("Petrosian object, " + str(self.ID) + " | Center Position: " + str(self.pos) + ", " +
                                                     "Petrosian Radius: " + str(self.petroR) + ", " +
                                                     "Redshift: " + str(self.z))
        # return(str(self.ID) + str(self.pos) + str(self.iso_radii) + str(self.SB) +
        #        str(self.SBerr) + str(self.iso_eps) + str(self.aper) + str(self.petroR))

    def print_all(self):
        print("\n" +
              "ID: " + str(self.ID) + '\n' +
              "Redshift: " + str(self.z) + '\n' +
              "Pos: " + str(self.pos) + '\n' +
              "Radii length: " + str(len(self.iso_radii)) + '\n' +
              "SB length: " + str(len(self.SB)) + '\n' +
              "SB Err length: " + str(len(self.SBerr)) + '\n' +
              "Eps: " + str(len(self.iso_eps)) + '\n' +
              str(self.aper) + '\n' +
              "PetroR: " + str(self.petroR))
        return

    def toKpc(self):
        return ((SPEED_OF_LIGHT*self.z) / H0) * self.petroR * PIX_SCALE * (np.pi/(180*3600)) * 1000

def quick_plot(data=None, title="Default" , cmap='magma', interpolation='antialiased', show=True):
    z1, z2 = ZScaleInterval().get_limits(values=data)
    if cmap=='magma':
        plt.imshow(data, origin="lower", cmap=cmap, interpolation=interpolation, vmin=z1, vmax=z2)
    else:
        plt.imshow(data, origin="lower", cmap=cmap, interpolation=interpolation)
    plt.title(title)
    if show:
        plt.show()
    return

def universalToKpc(z, d):
    return ((SPEED_OF_LIGHT*z) / H0) * d * PIX_SCALE * (np.pi/(180*3600)) * 1000

def image_segmintation(data, threshold=0.5, display=True):
    convolved_FWHM = 3.0
    convolved_size = 5
    segment_npixels = 10

    print("Plotting raw data...")
    quick_plot(data=data, title="Raw data")

    print("Convolving data with a 2D kernal...")
    kernel = make_2dgaussian_kernel(convolved_FWHM, size=convolved_size)
    convolved_data = convolve(data, kernel)
    if display:
        quick_plot(data=kernel, title="Kernal")

    print("Detecting sources in convolved data...")
    segment_map = detect_sources(convolved_data, threshold, npixels=segment_npixels)
    if display:
        print(segment_map)

    print("Deblend overlapping sources...")
    # segm_deblend = deblend_sources(convolved_data, segment_map,
    #                                npixels=10, nlevels=32, contrast=0.001,
    #                                progress_bar=True)
    # if display:
    #     plt.imshow(segm_deblend, origin='lower', cmap=segment_map.cmap,
    #                interpolation='nearest')
    #     plt.xlabel("[pixels]"); plt.ylabel("[pixels]")
    #     plt.title("Deblended Segmentation Image")
    #     plt.show()
    segm_deblend = segment_map
    if display:
        quick_plot(segment_map, title="Segmentation Image", cmap=segment_map.cmap, interpolation='nearest')

    print("Catalog sources...")
    cat = SourceCatalog(data, segm_deblend, convolved_data=convolved_data)

    apers = cat.make_kron_apertures()
    # print(apers[0].positions)

    tbl = cat.to_table()
    tbl['xcentroid'].info.format = '.2f'  # optional format
    tbl['ycentroid'].info.format = '.2f'

    sources_x = tbl['xcentroid']
    sources_y = tbl['ycentroid']
    sources_eps = tbl['eccentricity']

    if display:
        print('\n')
        print(cat)
        print(tbl)
        print(sources_x, sources_y, sources_eps)

    print("Setting Kron apertures...")
    # norm = simple_norm(data, 'sqrt')
    quick_plot(segment_map, title='kron apertures', cmap=segment_map.cmap, show=False)
    cat.plot_kron_apertures(color='green', lw=1.5)
    plt.show()

    return sources_x, sources_y, sources_eps, apers

def isophote_fit_image_aper(dat, aper, eps=0.01, perExtra=150):
    """
    Determine surface brights at points radius, r, outward using photoutils
    ---
    Input:  dat, numpy.array; intensity values for cropped area of fits file
            cen0, numpy.array; center point of galaxy
            rMax, int; max distance [pixels] from center that the isophotes will be calculated to
            nRings, int; number of isophotes to display later
    Output: isolist.sma, numpy.array; list of radii/sma values for isophotes
            isolist.intens, numpy.array; list of intensity/surface brightness values for isophotes
            isolist.int_err, numpy.array; 'The error of the mean intensity (rms / sqrt(# data points)).'
            isos, list; list of reconstructed ʻringsʻ/isophotes at some interval, r_max/n_rings
            cen_new, final calculated center of isophote calculating
    Notes:  Algorithum used is from Jedrzejewski (1987; MNRAS 226, 747)
            https://ui.adsabs.harvard.edu/abs/1987MNRAS.226..747J/abstract
    """
    z1, z2 = ZScaleInterval().get_limits(values=dat)  # MJy/sr

    cen = [aper.positions[0], aper.positions[1]] # Grab updated centers

    # plt.imshow(dat, origin='lower', vmin=z1, vmax=z2) # Plot ALL data from fits, bounded
    # aper.plot(color='r')

    g = EllipseGeometry(x0=cen[0], y0=cen[1], sma=aper.a, eps=eps, pa=(aper.theta / 180.0) * np.pi)
    ellipse = Ellipse(dat, geometry=g)
    isolist = ellipse.fit_image(maxsma=(aper.a*(perExtra/100))) # Creates isophotes using the geometry of 'g', so using above parameters as the bounds
    # print("Number of isophotes: ", len(isolist.to_table()['sma']))

    # # Plots the isophotes over some interval -- this part is PURELY cosmetic, it doesn't do anything
    # isos = [] # A list of isophote x-y positions to plot later
    # if nRings == -1:                            # nRings=-1 plots all the rings
    #     nRings = len(isolist.to_table()['sma'])
    # if nRings != 0 and len(isolist.to_table()['sma']) > 0: # Makes sure that there is data from the isophote fit
    #     rMax = isolist.to_table()['sma'][-1]  # Largest radius
    #     rings = np.arange(0, rMax, rMax / nRings)
    #     rings += rMax / nRings
    #     for sma in rings:
    #         iso = isolist.get_closest(sma) # Displayed isophotes are just the closest isophotes to a certain desired sma, but
    #                                        # there are more isophotes between the ones displayed.
    #         isos.append(iso.sampled_coordinates())
    #         plt.plot(iso.sampled_coordinates()[0], iso.sampled_coordinates()[1], color='g', linewidth=1)
    # if display:
    #     plt.show()

    return isolist.sma, isolist.intens, isolist.int_err, isolist.to_table()['ellipticity'], isolist

def plot_sb_profile(ID='', r=None, SB=None, err=None, sigma=10, r_forth=False, units=False, save=False):
    """
    Plot the surface brightness profile
    ---
    Input:  r, numpy.array; radius/semimajor axis of galaxy
            SB, numpy.array; surface brightness for each point of radius
            err, numpy.array; error of surface brightness calculation / meassurement error
            sigma, int; scales the error bars
            r_forth, bool; swaps mode to plot r to the 1/4
            units, bool; True=arcseconds, False=pixels
            save, bool; save plot or not
    Output: None
    """
    unit = '[pixels]'
    marker_size = 2
    if units:
        r = r * PIX_SCALE
        unit = '[arcsec]'

    # Plot SB vs radius [arcsec]
    plt.errorbar(r, SB, yerr=(err) * sigma, fmt='o', ms=marker_size)
    plt.xlabel("Radius, r " + unit)
    plt.title(SYS_TIME + "_" + str(ID) + '\nSurface Brightness Profile, ' + unit)
    plt.ylabel("Intensity, I [MJy/sr]")
    if save:
        plt.savefig(r"results\SBprofile_" + str(int(SYS_TIME)) + ".png")
    plt.show()

    return None

def petrosian_radius(radius=None, SB=None, eps=None, sens=0.01):
    adda = 0.2  # Target constant
    petro_r = 0 # Initalizing petrosian value

    for i in range(2, len(radius)):
        localSB = SB[i]
        a = radius[:i]
        eps_i = eps[:i]
        SB_i = SB[:i]

        b = a[-1] - (eps_i[-1] * a[-1])  # Semi-minor Axis
        SBtoR = simpson(y=SB_i, x=a) * 2 * np.pi
        area = np.pi * a[-1] * b

        integratedSB = SBtoR / area

        if abs(integratedSB - (adda*localSB)) < sens:
            petro_r = radius[i]
            break
    return petro_r

def world_to_pix(data, crd, targetPath):
    # Plot/Organize coords
    allCoordPix = []
    targetIDs = []


    targets = np.genfromtxt(targetPath, delimiter=',', skip_header=1, dtype=float)
    targets = targets[:, :4]
    targetIDs = targets[:, 0]
    targetZs = targets[:, 3]

    plt.imshow(data, origin="lower", cmap='magma', vmin=0, vmax=0.5)
    plt.title("Targets from Gus List over FITS-C1009-T008-NIRCAM-F090W")
    for t in targets:
        RA = t[1]
        DEC = t[2]
        coordWorld = SkyCoord(ra=RA, dec=DEC, unit="deg")
        coordPix = coordWorld.to_pixel(crd, 0)
        allCoordPix.append(np.array([coordPix[0], coordPix[1]]))
        plt.plot(coordPix[0], coordPix[1], marker='+', color='g')
    plt.show()
    return allCoordPix, targetIDs, targetZs

if __name__ == "__main__":
    mainPath = r'downloads\jw01181-c1009_t008_nircam_clear-f090w_i2d.fits'
    altPath=r'downloads/jw01181-c1009_t008_nircam_clear-f090w_i2d.fits'
    altPath2=r'downloads/jw01181-o004_t008_nircam_clear-f090w_i2d.fits'
    altPath3=r'downloads/jw01181-o001_t001_nircam_clear-f090w_i2d.fits'
    fileDesc = 'v4_c1009_t008'
    bin = 'SCI'
    sourceSens = 0.3 # smaller = more targets
    overlapSens = 40 # +/- number of pixels in range
    petroSens = 0.1
    extentOfDetect = 100 # % past max sma of isophotes
    tryLim = 50 # number of tries to fit petrosian
    tryIsoIncrease = 18 # % increase when attempting new fit, max @ 1000% for 50
    tryEpsIncrease = 0.0195 # increase of ellipticity when attempting new fit, max @ 0.99 for 50

    # OPEN FITS FILE
    #----------------------------------------------------------------------------------------------------------------
    print("Obtaining data from FITS...")
    with fits.open(altPath) as hdul:
        hdu = hdul[bin]
        data = hdu.data
        hdr = hdu.header
        datacoords = WCS(hdr)

    # OPEN TARGET LIST
    #----------------------------------------------------------------------------------------------------------------
    targetPath = r'targets.csv'
    print("Sorting target list...")
    targetsPix, targetIDs, targetZs = world_to_pix(data, datacoords, targetPath)

    # SOURCE DETECTION
    #----------------------------------------------------------------------------------------------------------------
    print("Detecting sources (segmenting image)...")
    sources_x, sources_y, sources_eps, apers = image_segmintation(data, threshold=sourceSens, display=False)
    positions = []
    for i in range(len(sources_x)):
        positions.append(np.array([sources_x[i], sources_y[i]]))

    # DETERMINE SOURCE OVERLAP WITH TARGET LIST
    #----------------------------------------------------------------------------------------------------------------
    overlappedPositions, overlappedEps, overlappedApers, overlappedIDs, overlappedZs = [], [], [], [], []
    for i in range(len(targetsPix)):
        for j in range(len(positions)):
            rangex = abs(positions[j][0] - targetsPix[i][0])
            rangey = abs(positions[j][1] - targetsPix[i][1])
            if rangex < overlapSens and rangey < overlapSens:
                overlappedPositions.append(np.array([positions[j][0], positions[j][1]]))
                overlappedEps.append(sources_eps[j])
                overlappedApers.append(apers[j])
                overlappedIDs.append(targetIDs[i])
                overlappedZs.append(targetZs[i])


    # MAKE PETRO OBJECTS
    #----------------------------------------------------------------------------------------------------------------
    petroObjs = []
    for i in range(len(overlappedPositions)):
        tempObj = petrosianObject(ID = int(overlappedIDs[i]), z = overlappedZs[i], pos = overlappedPositions[i], aper=overlappedApers[i], iso_eps=float(overlappedEps[i]))
        petroObjs.append(tempObj)
        # tempObj.print_all()

    # REMOVE DUPLICATES
    #----------------------------------------------------------------------------------------------------------------
    seen = []
    seenObj = []
    for obj in petroObjs:
        if obj.ID not in seen:
            seen.append(obj.ID)
            seenObj.append(obj)
    petroObjs = seenObj

    # CHECK OVERLAP
    #----------------------------------------------------------------------------------------------------------------
    plt.figure(figsize=(10, 10))
    quick_plot(data, title='Overlap from Gus Targets & Source Detection \n N=' +
                           str(len(overlappedPositions) - (len(overlappedPositions) - len(seenObj))), show=False)
    for t in targetsPix:
        plt.plot(t[0], t[1], marker='+', color='g')
    for obj in petroObjs:
        plt.plot(obj.pos[0], obj.pos[1], marker='x', color='b')
    # plt.xlim(-1000, 4500); plt.ylim(2500, 8250)
    plt.show()
    print("Number Overlapped: ", len(overlappedPositions) - (len(overlappedPositions) - len(seenObj)))
    print("Number Doubled: ", len(overlappedPositions) - len(seenObj))
    print("Expected: ", len(targetsPix))

    # PROCESSING
    #----------------------------------------------------------------------------------------------------------------
    fatalCount = 0
    for i in range(len(petroObjs)):
        print("[", i+1, '/', len(petroObjs), "]")
        fatal = False
        # Isophote Fit
        print("[", petroObjs[i].ID, "] Fiting isophotes...")
        localEps = 0.01
        attemptIso = 0
        while attemptIso <= tryLim:
            tempRadii, tempSB, tempSBerr, tempEps, tempIsolist = isophote_fit_image_aper(dat=data,
                                                                                         aper=petroObjs[i].aper,
                                                                                         eps=localEps,
                                                                                         perExtra=extentOfDetect)
            if len(tempRadii) > 0 or attemptIso == tryLim:
                petroObjs[i].iso_radii = tempRadii
                petroObjs[i].SB = tempSB
                petroObjs[i].SBerr = tempSBerr
                petroObjs[i].iso_eps = tempEps
                petroObjs[i].isolist = tempIsolist
                break  # Leave while loop (petrosian found)
            else:
                localEps += tryEpsIncrease
                print("[", petroObjs[i].ID, "] Fit Failed, altering ellipticity ",
                      tryEpsIncrease, " (New: ", localEps, ")")
                attemptIso += 1
        if len(tempRadii) == 0:
            print("![", petroObjs[i].ID, "] FATAL -- NO FIT DETERMINED!")
            fatal = True
            fatalCount += 1

        if not fatal:
            # PETROSIAN RADIUS
            print("[", petroObjs[i].ID, "] Calculating petrosian radii...")
            realPetroObjs = []
            attemptPetro = 0
            localExtentOfDetect = extentOfDetect
            while attemptPetro <= tryLim:
                petro_r = petrosian_radius(radius=petroObjs[i].iso_radii, SB=petroObjs[i].SB,
                                           eps=petroObjs[i].iso_eps, sens=petroSens)
                if petro_r > 0:
                    petroObjs[i].petroR = petro_r
                    realPetroObjs.append(petroObjs[i])
                    break
                else:
                    localExtentOfDetect += tryIsoIncrease
                    print("[", petroObjs[i].ID, "] No petrosian found, extending range by", tryIsoIncrease,
                          "% (Now: ", localExtentOfDetect, "%)")
                    tempRadii, tempSB, tempSBerr, tempEps, tempIsolist = isophote_fit_image_aper(dat=data,
                                                                                                 aper=petroObjs[i].aper,
                                                                                                 eps=localEps,
                                                                                                 perExtra=localExtentOfDetect)
                    petroObjs[i].iso_radii = tempRadii
                    petroObjs[i].SB = tempSB
                    petroObjs[i].SBerr = tempSBerr

                    attemptPetro += 1

            if petro_r == 0:
                print("![", petroObjs[i].ID, "] FATAL -- NO PETROSIAN RADIUS DETERMINED!")
                fatal = True
                fatalCount += 1
        print('\n')
    print('Success Rate of Petrosian: ', (len(petroObjs) - fatalCount)/len(petroObjs)*100, '% [', (len(petroObjs) - fatalCount), '/', len(petroObjs), ']')

    # DISPLAY
    #----------------------------------------------------------------------------------------------------------------
    os.mkdir('images/' + fileDesc + '/' + str(SYS_TIME))
    crop = 150
    nRings = 15

    for obj in petroObjs:
        current_petroR = round(obj.toKpc(), 2)

        z1, z2 = ZScaleInterval().get_limits(values=data)
        fig = plt.figure(figsize=(12, 8))
        fig.suptitle('ID [' + str(obj.ID) + ']' + '\n' +
                     # 'Center: (' + str(round(obj.pos[0], 2)) + ', ' + str(round(obj.pos[1], 2)) + ') | ' +
                     'Petrosian Radius: ' + str(current_petroR) + ' [kpc] | ' +
                     'Redshift: ' + str(round(obj.z, 2)))

        # Raw Data
        # Raw Data
        # ax1 = plt.subplot(223)
        # crop = 70
        # ax1.imshow(data, origin="lower", cmap='magma', vmin=z1, vmax=z2)
        # cenx, ceny = int(obj.pos[0]), int(obj.pos[1])
        # ax1.set_xlim(cenx - crop, cenx + crop)
        # ax1.set_ylim(ceny - crop, ceny + crop)
        # ax1.set_xlabel('[pixels]')
        # ax1.set_ylabel('[pixels]')
        ax1 = plt.subplot(223)
        cenx, ceny = int(obj.pos[0]), int(obj.pos[1])
        ax1.imshow(data, origin="lower", cmap='magma', vmin=z1, vmax=z2)
        ax1.set_xlim(cenx - crop, cenx + crop)
        ax1.set_ylim(ceny - crop, ceny + crop)
        ax1.set_xlabel('[pixels]')
        ax1.set_ylabel('[pixels]')


        # Isophote Rings
        ax2 = plt.subplot(224)
        ax2.imshow(data, origin="lower", cmap='magma', vmin=z1, vmax=z2)
        if nRings == -1:  # nRings=-1 plots all the rings
            nRings = len(obj.isolist.to_table()['sma'])
        if nRings != 0 and len(obj.isolist.to_table()['sma']) > 0:  # Makes sure that there is data from the isophote fit
            rMax = obj.isolist.to_table()['sma'][-1]  # Largest radius
            rings = np.arange(0, rMax, rMax / nRings)
            rings += rMax / nRings
            for sma in rings:
                iso = obj.isolist.get_closest(sma)  # Displayed isophotes are just the closest isophotes to a certain desired sma, but
                                                    # there are more isophotes between the ones displayed.
                ax2.plot(iso.sampled_coordinates()[0], iso.sampled_coordinates()[1], color='g', linewidth=1)
        ax2.set_xlim(cenx - crop, cenx + crop)
        ax2.set_ylim(ceny - crop, ceny + crop)
        ax2.set_xlabel('[pixels]')
        ax2.set_ylabel('[pixels]')

        # Surface Brightness plot
        ax3 = plt.subplot(211)
        ax3.errorbar(universalToKpc(obj.z, obj.iso_radii), obj.SB, yerr=(obj.SBerr) * 10, fmt='o', ms=2)
        ax3.axvline(x=current_petroR, color='r', label='Petrosian Radius = '+str(current_petroR)+' [kpc]')
        ax3.set_xlabel('radius [kpc]')
        ax3.set_ylabel('Intensity [MJy/sr]')
        ax3.legend()

        plt.savefig('images/' + fileDesc + '/' + str(SYS_TIME)  + '/' + str(obj.ID) + '_' + str(SYS_TIME) + '.png', dpi=300)
        plt.show()

    # WRITE RADII & ID TO FILE
    #----------------------------------------------------------------------------------------------------------------
    with (open('petrosians/'+str(fileDesc)+'_petrosians.csv', 'w') as f):
        print('Wrote to...', 'petrosians/'+str(fileDesc)+'_petrosians.csv')
        f.write('File: '+altPath+'\n')
        f.write('ID,PETROSIANPIX,PETROSIANKPC,PIXCENTERX,PIXCENTERY,REDSHIFT\n')
        for obj in petroObjs:
            line = str(obj.ID) + ',' + str(obj.petroR) + ',' + str(obj.toKpc()) + ',' + str(obj.pos[0]) + ',' + str(obj.pos[1]) + ',' + str(obj.z) + '\n'
            f.write(line)




