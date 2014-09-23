# This is a Pyxis recipe for JVLA 3C147 calibration.
# Note that all Pyxis recipes and configurations from your current directory (pyxis-*.{py,conf}) are 
# loaded automatically when you import Pyxis in Python, or when you run the pyxis command-line tool.

import Pyxis

# Pyxides contains application-specific modules.
# In this case load the calibration module, and the imager.
# Note that Pyxides is implicitly added to the include path, so no need to specify it at import
import mqt,stefcal,imager,lsm,std,ms

# we use this below
import pyfits
import numpy

## 1. Variable assignments
# Note that any variables set here can be overridden from the pyxis command line using VAR=VALUE. You can also choose to split 
# this part off into a separate pyxis*.conf file, if it gets too big.

# default MS and DDID
MS_Template = '3C147_nobl_spw${ms.DDID}.MS'
ms.DDID = 2
# Note that the magic "v" object provides access to "superglobal" variables. Superglobals are propagated across
# all modules. As a result of the above statement, there's now an identical MS and DDID variable set in every Pyxides 
# module (which in this case include 'cal', 'ms', 'imager' and 'mqt', the latter two imported by 'cal'), as well 
# as an MS and DDID variable here. Superglobals are handy, but overreliance on them can lead to namespace pollution 
# and confusion, so Pyxis uses them very sparingly, i.e. only for truly global things like MS, DDID, LSM, etc.
# 
# Note also that if we say "MS='dum'" now, this will set a global MS variable within the context of this particular script,
# but not the "MS" superglobal. This is another source of confusion, and another reason to assign superglobals sparingly.
# Always assign superglobals with v.MS=, not MS=!!!

# polarized images by default, and extract polarization info in pybdsm
imager.stokes="IQUV"
lsm.PYBDSM_POLARIZED = True     

imager.IMAGE_CHANNELIZE = 0        # 0 means make a single image for the whole band (1 makes a cube)

## Some more globals in the imager module
imager.ifrs=""
imager.mode="channel"
imager.weight="briggs"
imager.niter=10000
imager.gain=.1
imager.threshold=0

_ms_config = [];
_ms_config_lastms = None;

def msconfig (pattern,*args,**kw):
  """Adds MS-specific configuration function or variable assignemnys.
  'pattern', e.g. "3C147-C-*" is matched (using shell wildcards) against the MS name.
  'args' have two forms: either callable functions (which are expected to do configurations
  and variable asignment, or they should come as 'name',value pairs (or keyword arguments)
  Whenever runcal() below is called, it will see which patterns the MS matches (in the order
  that they were added), and perform configuration according to this.
  
  Example: msconfig("3C147-C*",cconf,'imager.cellsize','2arcsec',LSMBASE='3C147-C.LSM');
  This will call cconf(), and set imager.cellsize='2arcsec' and v.LSMBASE='3C147-C.LSM' when
  the MS name matches the pattern"""
  if not isinstance(pattern,str):
    abort("invalid msconfig() pattern '$pattern'");
  cmdlist = [];
  while args:
    if callable(args[0]):
      cmdlist.append(args[0]);
      args = args[1:];
    elif len(args)<2 or not isinstance(args[0],str):
      abort("invalid msconfig() argument '%s'"%str(args[0]));
    else:
      cmdlist.append(args[0:2]);
      args = args[2:];
  cmdlist += list(kw.iteritems());
  _ms_config.append((pattern,cmdlist));
  
def _MSCONFIG_Template ():
  import fnmatch
  global _ms_config_lastms;
  if MS != _ms_config_lastms:
    _ms_config_lastms = MS;
    for pattern,cmdlist in _ms_config:
      if fnmatch.fnmatch(MS,pattern):
        info("$MS matches msconfig pattern $pattern:");
        for cmd in cmdlist:
          if callable(cmd):
            info("  calling %s()"%cmd.__name__);
            cmd();
          else:
            info("  assigning %s=%s"%cmd);
            assign(*cmd);
  return MS

def dconf ():
  global NPIX,CLEAN_THRESH,THRESH_ISL,THRESH_PIX
  """Sets config and imaging options for VLA-D"""
  imager.npix = NPIX = 2048
  imager.cellsize = "8arcsec"
  imager.wprojplanes = 0
  imager.CLEAN_ALGORITHM = "clark"
  v.LSMREF = "${MS:BASE}.refmodel.lsm.html"
  THRESH_PIX,THRESH_ISL = 50,15
  CLEAN_THRESH = ".5mJy",".12mJy",".06mJy"

def cconf ():
  global NPIX,CLEAN_THRESH,THRESH_ISL,THRESH_PIX
  """Sets config and imaging options for VLA-C"""
  imager.npix = NPIX = 4096
  imager.cellsize = "2arcsec"
  imager.wprojplanes = 128
  imager.CLEAN_ALGORITHM = "csclean"
  v.LSMREF = "${MS:BASE}.refmodel.lsm.html"
  THRESH_PIX,THRESH_ISL = 50,15
  CLEAN_THRESH = ".4mJy",".1mJy",".05mJy"
  
# Now for things specific to this script here.
dconf()

# Filenames for the LSM at various stages. 
# Variables ending in _Template are automatically be re-evaluated when e.g. DDID changes, 
# thus generating the actual LSM0, LSM1, LSM2 variables
SUFFIX_Template = "${-spw<ms.DDID}${-cb<CHBL}"
LSM0_Template = "$LSMBASE.lsm.html"
LSM1_Template = "$DESTDIR/$LSMBASE$SUFFIX+pybdsm.lsm.html"
LSM2_Template = "$DESTDIR/$LSMBASE$SUFFIX+pybdsm+cc.lsm.html"
LSM3_Template = "$DESTDIR/$LSMBASE$SUFFIX+pybdsm+cc.lsm.html"
LSM_CCMODEL_Template = "$DESTDIR/$LSMBASE$SUFFIX+ccmodel.fits"
# this is a reference LSM from which we transfer dE tags
LSMREF = "3C147-refmodel.lsm.html"

LOG_Template = "${OUTDIR>/}log-${MS:BASE}$SUFFIX.txt"
DESTDIR_Template = "${OUTDIR>/}plots-${MS:BASE}$SUFFIX"
OUTFILE_Template = "${DESTDIR>/}${MS:BASE}$SUFFIX${-s<STEP}${-<LABEL}"


## 2. Procedures
# Procedures are invoked from the command line (i.e. "pyxis runcal" or "pyxis per_ms[runcal]").
# Think of them as recipes or something like that.
# I've tried to keep this one simple and linear, with everything determined by the variables set above.
# The net result of this is that any processing stage can be re-created interactively in ipython, by 
# simply typing
# : import Pyxis
# : LSM=LSM1
# : stefcal.stefcal(restore=True);
# You can also restart the calibration at a specific step by supplying a goto_step>0 here.
def runcal (goto_step=1):
  ## initial calibration
  if goto_step > 1:
    info("########## restarting calibration from step $goto_step");
  # Calibration step -- this is just a user-defined label used in filenames (etc. "blahblah_s1"), which serves to keep the output from each step
  # of a pipeline separate. If this is numeric, then functions such as stefcal.stefcal() will increment it automatically first thing. Otherwise you can set
  # it yourself to some more fancy label. Here we also provide a way to hop to  particular step via goto_step
  v.STEP = goto_step-1;
  
  if goto_step < 2:
    # set the superglobal LSM
    v.LSM = LSM0
    info("########## solving for G with initial LSM");
    # no w-proj for dirty map to save time
    stefcal.stefcal(stefcal_reset_ifr_gains=True,dirty=dict(wprojplanes=0),restore=True);
    info("########## running source finder and updating model");
    ## now run pybdsm on restored image, output LSM will be given by variable cal.PYBDSM_OUTPUT
    lsm.pybdsm_search(threshold=7);
    ### merge new sources into sky model, give it a new name ($LSM1)
    lsm.tigger_convert("$LSM -a ${lsm.PYBDSM_OUTPUT} $LSM1 --rename -f");
  
  if goto_step < 3:
    info("########## solving for G with updated LSM (initial+pybdsm)");
    v.LSM = LSM1
    stefcal.stefcal(dirty=dict(wprojplanes=0));
    
  if goto_step < 4:
    info("########## re-solving for G to apply IFR solutions");
    stefcal.stefcal(dirty=dict(wprojplanes=0),restore=True);
    
    info("########## adding clean components to LSM");
    CCMODEL = II("ccmodel-ddid${ms.DDID}.fits");  # note the per-style variable interpolation done by the II() function
    ff = pyfits.open(imager.MODEL_IMAGE);
    dd = ff[0].data;
    dd *= 1.0769     # scale up to compensate for selfcal flux suppression
    # dd[dd<0] = 0;  # remove negative components
    ff.writeto(CCMODEL,clobber=True);
    # add model image to LSM
    lsm.tigger_convert("$LSM $LSM2 --add-brick=ccmodel:$CCMODEL:2 -f");

  if goto_step < 5:          
    info("########## solving for G with updated LSM (inital+pybdsm+cc)");
    v.LSM = LSM2
    stefcal.stefcal(dirty=dict(wprojplanes=0));
    
  if goto_step < 6:
    info("########## running DD solutions");
    v.LSM = LSM2
    # now, set dE tags on sources
    lsm.transfer_tags(LSMREF,LSM,tags="dE",tolerance=45*ARCSEC);
  
    # make final image
    stefcal.stefcal(dirty=dict(wprojplanes=0),diffgains=True,restore=True,label="dE"); 

def c_cal (goto_step=1):
  """Calibration for C-config data"""
  ## initial calibration
  if goto_step > 1:
    info("########## restarting calibration from step $goto_step");
  # Calibration step -- this is just a user-defined label used in filenames (etc. "blahblah_s1"), which serves to keep the output from each step
  # of a pipeline separate. If this is numeric, then functions such as stefcal.stefcal() will increment it automatically first thing. Otherwise you can set
  # it yourself to some more fancy label. Here we also provide a way to hop to  particular step via goto_step
  v.STEP = goto_step-1;
  
  if goto_step < 2:
    # set the superglobal LSM
    v.LSM = LSM0
    info("########## solving for G with initial LSM");
    # no w-proj for dirty map to save time
    stefcal.stefcal(stefcal_reset_all=True,
        dirty=dict(wprojplanes=0,npix=NPIX),
        restore=dict(npix=NPIX,threshold=CLEAN_THRESH[0],wprojplanes=128));
    info("########## running source finder and updating model");
    ## now run pybdsm on restored image, output LSM will be given by variable cal.PYBDSM_OUTPUT
    ### NB: select on radius to exclude any artefacts picked up around 3C147 itself
    lsm.pybdsm_search(thresh_pix=THRESH_PIX,thresh_isl=THRESH_ISL,select="r.gt.30s");
    ### merge new sources into sky model, give it a new name ($LSM1)
    lsm.tigger_convert("$LSM -a ${lsm.PYBDSM_OUTPUT} $LSM1 --rename -f");
  
  if goto_step < 3:
    info("########## solving for G+dE with updated LSM (initial+pybdsm)");
    v.LSM = LSM1
    # now, set dE tags on sources
    lsm.transfer_tags(LSMREF,LSM,tags="dE",tolerance=45*ARCSEC);
    stefcal.stefcal(stefcal_reset_all=True,diffgains=True,dirty=dict(wprojplanes=0,npix=NPIX));
    
  if goto_step < 4:
    info("########## re-solving for G to apply IFR solutions");
    v.LSM = LSM1
    stefcal.stefcal(diffgains=True,diffgain_apply_only=True,
      dirty=dict(wprojplanes=0,npix=NPIX),
      restore=dict(npix=NPIX,threshold=CLEAN_THRESH[1]));
    
    info("########## adding clean components to LSM");
    ff = pyfits.open(imager.MODEL_IMAGE);
    dd = ff[0].data;
    dd *= 1.0769     # scale up to compensate for selfcal flux suppression
    # dd[dd<0] = 0;  # remove negative components
    ff.writeto(LSM_CCMODEL,clobber=True);
    # add model image to LSM
    lsm.tigger_convert("$LSM $LSM2 --add-brick=ccmodel:$LSM_CCMODEL:2 -f");

  if goto_step < 5:
    info("########## re-running DD solutions");
    v.LSM = LSM2
    # make final image
    stefcal.stefcal(dirty=dict(wprojplanes=0,npix=NPIX),diffgains=True,
      restore=dict(npix=NPIX,threshold=CLEAN_THRESH[2]),
      label="dE"); 

  # make per-channel cube
  makecube(NPIX);
  # make noise images     
  makenoise();
  
def makenoise ():  
  # make noise images     
  addnoise();
  imager.make_image(channelize=1,dirty_image="$OUTFILE.noisecube.fits",npix=256,wprojplanes=0,stokes="I",column="MODEL_DATA");
  imager.make_image(dirty_image="$OUTFILE.noise.fits",npix=256,wprojplanes=0,stokes="I",column="MODEL_DATA");
  noise = pyfits.open(II("$OUTFILE.noise.fits"))[0].data.std();
  info(">>> maximum noise value is %.2f uJy"%(noise*1e+6));
  
def saveconf ():
  if OUTDIR and OUTDIR != ".":
    x.sh("cp pyxis-RP3C147.py pyxis-RP3C147.conf tdlconf.profiles $OUTDIR");

DE_SMOOTHING = 18,16

def jointcal (goto_step=1,last_step=10,lsmbase=None,STEPS=None):
  """Calibration for joint C and D-config data"""
  info(">>>>>>>>>>>>> output directory is $OUTDIR. Please set OUTDIR explicitly to override");

  # setup LSM filenames based on the full MS
  # note that these get interpolated once and for all here (and the _Template definitions above
  # get cancelled due to the explicit assignment here). The reason for doing it like this
  # is because I don't want these names to be changing due to the templates every time the 
  # MS changes in a per(MS) call.
  v.FULLMS = MS
  LSM1 = II("$DESTDIR/$LSMBASE$SUFFIX+pybdsm.lsm.html");
  LSM2 = II("$DESTDIR/$LSMBASE$SUFFIX+pybdsm2.lsm.html");
  LSM3 = II("$DESTDIR/$LSMBASE$SUFFIX+pybdsm2+cc.lsm.html");
  LSM_CCMODEL = II("$DESTDIR/$LSMBASE$SUFFIX+ccmodel.fits");
  saveconf()

  stefcal.STEFCAL_DIFFGAIN_SMOOTHING = DE_SMOOTHING;

  # make MS list from sub-MSs
  import glob
  v.MS_List = glob.glob(MS+"/SUBMSS/*MS");
  info("MS list is $MS_List");
  if not MS_List:
    abort("No sub-MSs found");
  
  imager.npix = NPIX = 4096
  imager.cellsize = "2arcsec"
  imager.wprojplanes = 128
  imager.CLEAN_ALGORITHM = "csclean"
  v.LSMREF = "${MS:BASE}.refmodel.lsm.html"
  THRESH_PIX,THRESH_ISL = (50,10),(15,5)
  CLEAN_THRESH = ".4mJy",".1mJy",".05mJy"
  stefcal.STEFCAL_STEP_INCR = 0 # precvent stefcal from auto-incrementing v.STEP: we set the step counter explicitly here
  
  if STEPS is None:
    STEPS = list(numpy.arange(goto_step,last_step+.1,.5));
  STEPS = map(float,STEPS);

  if STEPS[0] != 1:
    info("########## restarting calibration from step %.1f"%STEPS[0]);

  if lsmbase:
    LSMBASE = lsmbase;

  ## initial calibration
  
  if 1. in STEPS:
    info("########## step 1: solving for G with initial LSM");
    v.LSM,v.STEP = LSM0,1
    per_ms(jointcal_g);
    
  if 1.5 in STEPS:
    info("########## step 1.5: making joint image");
    v.LSM,v.STEP = LSM0,1
    v.MS = FULLMS
    # initial model is total flux only, made from a 2x size image to catch distant sources
    imager.make_image(dirty=False,stokes="I",restore=dict(npix=NPIX*2,threshold=CLEAN_THRESH[0],wprojplanes=128),restore_lsm=False);
    info("########## running source finder and updating model");
    ## now run pybdsm on restored image, output LSM will be given by variable cal.PYBDSM_OUTPUT
    ### NB: select on radius to exclude any artefacts picked up around 3C147 itself
    lsm.pybdsm_search(thresh_pix=THRESH_PIX[0],thresh_isl=THRESH_ISL[0],select="r.gt.30s",pol=False);
    ### merge new sources into sky model, give it a new name ($LSM1)
    lsm.tigger_convert("$LSM -a ${lsm.PYBDSM_OUTPUT} $LSM1 --rename -f");

  # if 2. in STEPS:
  #   info("########## step 2: repeating G solution");
  #   v.LSM,v.STEP = LSM1,2
  #   v.MS = FULLMS  
  #   per_ms(jointcal_g);
    
  if 2. in STEPS:
    info("########## step 2: initial dE solution");
    v.LSM,v.STEP = LSM1,2
    v.MS = FULLMS  
    # now, set dE tags on sources
    lsm.transfer_tags(LSMREF,LSM,tags="dE",tolerance=45*ARCSEC);
    per_ms(jointcal_de_reset);

  if 3. in STEPS:
    info("########## step 3: re-solving for G to apply IFR solutions");
    v.LSM,v.STEP = LSM1,3
    v.MS = FULLMS
    per_ms(jointcal_de_apply);
    info("########## running source finder and updating model");
    v.MS = FULLMS
    imager.make_image(dirty=False,stokes="IV",restore=dict(npix=NPIX,threshold=CLEAN_THRESH[1],wprojplanes=128),restore_lsm=False);
    ## now run pybdsm on restored image, output LSM will be given by variable cal.PYBDSM_OUTPUT
    ### NB: select on radius to exclude any artefacts picked up around 3C147 itself
    lsm.pybdsm_search(thresh_pix=THRESH_PIX[1],thresh_isl=THRESH_ISL[1],select="r.gt.30s");
    ### merge new sources into sky model, give it a new name ($LSM1)
    lsm.tigger_convert("$LSM -a ${lsm.PYBDSM_OUTPUT} $LSM2 --rename -f");

  if 4. in STEPS:
    info("########## step 4: solving for G+dE with updated LSM (initial+pybdsm^2)");
    v.MS = FULLMS
    v.LSM,v.STEP = LSM2,4
    lsm.transfer_tags(LSMREF,LSM,tags="dE",tolerance=45*ARCSEC);
    per_ms(jointcal_de);
    v.MS = FULLMS
    imager.make_image(dirty=False,stokes="IV",restore=dict(npix=NPIX,threshold=CLEAN_THRESH[1],wprojplanes=128),restore_lsm=False);
    info("########## adding clean components to LSM");
    ff = pyfits.open(imager.MODEL_IMAGE);
    dd = ff[0].data;
    dd *= 1.0769     # scale up to compensate for selfcal flux suppression
    # dd[dd<0] = 0;  # remove negative components
    ff.writeto(LSM_CCMODEL,clobber=True);
    # add model image to LSM
    lsm.tigger_convert("$LSM $LSM3 --add-brick=ccmodel:$LSM_CCMODEL:2 -f");

  if 5. in STEPS:
    info("########## step 5: re-running DD solutions");
    v.MS = FULLMS
    v.LSM,v.STEP = LSM3,5
    per_ms(jointcal_de_final);
    
  if 5.5 in STEPS:
    info("########## step 5.5: making joint image");
    v.MS = FULLMS
    v.LSM,v.STEP = LSM3,5
    imager.make_image(dirty=False,stokes="IQUV",restore=dict(npix=NPIX,threshold=CLEAN_THRESH[2],wprojplanes=128),restore_lsm=True);
    
  if 6. in STEPS:
    info("########## step 6: noise sim");
    per_ms(lambda:makecube(stokes="IQUV"));
    v.LSM,v.STEP = LSM3,5
    v.MS = FULLMS;
    makecube(stokes="IQUV");
    makenoise();
    
def jointcal_g ():
  stefcal.stefcal(stefcal_reset_all=True,dirty=dict(wprojplanes=0,npix=NPIX),restore=False);
  
def jointcal_de_reset ():
  stefcal.stefcal(stefcal_reset_all=True,diffgains=True,dirty=dict(wprojplanes=0,npix=NPIX),restore=False);
    
def jointcal_de_apply ():
  stefcal.stefcal(diffgains=True,diffgain_apply_only=True,
    dirty=dict(wprojplanes=0,npix=NPIX),restore=False);

def jointcal_de ():
  stefcal.stefcal(diffgains=True,dirty=dict(wprojplanes=0,npix=NPIX),restore=False);

def jointcal_de_final ():
  stefcal.stefcal(diffgains=True,dirty=dict(wprojplanes=0,npix=NPIX),restore=False); # ,options=dict(stefcal_diagonal_ifr_gains='full'))  

def makecube (npix=512,stokes="I"):
  imager.make_image(channelize=1,dirty_image="$OUTFILE.cube.fits",npix=npix,wprojplanes=0,stokes=stokes);
  
def swapfields (f1,f2):
  """Swaps two fields in an MS"""
  info("swapping FIELDs $f1 and $f2 in $MS");
  field = ms.msw(subtable="FIELD");
  for name in field.colnames():
    info("swapping column $name");
    col = field.getcol(name);
    col[f1],col[f2] = col[f2],col[f1];
    field.putcol(name,col);
  field.close();
  tab = ms.msw();
  fcol = tab.getcol("FIELD_ID");
  r1 = (fcol==f1)
  r2 = (fcol==f2)
  fcol[r1] = f2
  fcol[r2] = f1
  tab.putcol("FIELD_ID",fcol);
  tab.close();

def fix_antpos ():
  anttab = ms.msw(subtable="ANTENNA");
  pos = anttab.getcol("POSITION");
  wh = pos[:,1]>0; 
  if wh.any():
    info(wh.sum(),"VLA dishes appear to be located in India. Moving them back to NM.")
    pos[wh,1] = -pos[wh,1];
    anttab.putcol("POSITION",pos);
  else:
    info("$MS antenna positions seem right, nothing to do")


SEFD = 350  
INTEGRATION = 0
  
def compute_vis_noise (noise=0):
  tab = ms.ms().query("FIELD_ID==%d"%ms.FIELD);
  spwtab = ms.ms(subtable="SPECTRAL_WINDOW");
  freq0 = spwtab.getcol("CHAN_FREQ")[ms.SPWID,0];
  global WAVELENGTH
  WAVELENGTH = 300e+6/freq0
  bw = spwtab.getcol("CHAN_WIDTH")[ms.SPWID,0];
  dt = INTEGRATION or tab.getcol("EXPOSURE",0,1)[0];
  dtf = (tab.getcol("TIME",tab.nrows()-1,1)-tab.getcol("TIME",0,1))[0]
  # close tables properly, else the calls below will hang waiting for a lock...
  tab.close();
  spwtab.close();
  info(">>> $MS freq %.2f MHz (lambda=%.2fm), bandwidth %.2g kHz, %.2fs integrations, %.2fh synthesis"%(freq0*1e-6,WAVELENGTH,bw*1e-3,dt,dtf/3600));
  if not noise:
    noise = SEFD/math.sqrt(2*bw*dt);
    info(">>> SEFD of %.2f Jy gives per-visibility noise of %.2f mJy"%(SEFD,noise*1000));
  else:
    info(">>> using per-visibility noise of %.2f mJy"%(noise*1000));
  return noise;

def addnoise (noise=0,rowchunk=100000):
  """adds noise to MODEL_DATA, writes to CORRECTED_DATA""";
  # compute expected noise
  noise = compute_vis_noise(noise);
  # fill MS with noise
    # setup stefcal options and run 
  info("Running turbo-sim to add noise to data");
  # setup args
  args = [ """${ms.MS_TDL} ${ms.CHAN_TDL} ms_sel.ms_ifr_subset_str=${ms.IFRS} noise_stddev=%g"""%noise ];
  mqt.run("${mqt.CATTERY}/Siamese/turbo-sim.py","simulate",section="addnoise",args=args);

  
