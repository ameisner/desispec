"""
Run integration test for quicklook pipeline

python -m desispec.test.integration_test_quicklook
"""
import os
import sys
import argparse
import desimodel.io
import desisim.io
import desispec.pipeline as pipe
import desispec.log as logging
from desispec.util import runcmd
from desispec.quicklook import qlconfig

desi_templates_available = 'DESI_ROOT' in os.environ
desi_root_available = 'DESI_ROOT' in os.environ

def check_env(args=None):
    """
    Check required environment variables; raise RuntimeException if missing
    """
    log = logging.get_logger()
    #- template locations
    missing_env = False

    if 'DESI_BASIS_TEMPLATES' not in os.environ:
        log.warning('missing $DESI_BASIS_TEMPLATES needed for simulating spectra'.format(name))
        missing_env = True

    if not os.path.isdir(os.getenv('DESI_BASIS_TEMPLATES')):
        log.warning('missing $DESI_BASIS_TEMPLATES directory')
        log.warning('e.g. see NERSC:/project/projectdirs/desi/spectro/templates/basis_templates/v1.0')
        missing_env = True

    for name in (
        'DESI_SPECTRO_SIM', 'PIXPROD', 'DESI_SPECTRO_DATA', 'DESI_SPECTRO_REDUX', 'DESIMODEL'):
        if name not in os.environ:
            log.warning("missing ${}".format(name))
            missing_env = True

    if missing_env:
        log.warning("Why are these needed?")
        log.warning("    Simulations written to $DESI_SPECTRO_SIM/$PIXPROD")
        log.warning("    Raw data read from $DESI_SPECTRO_DATA")
        log.warning("    Spectro/QuickLook pipeline output written to $DESI_SPECTRO_REDUX")
        log.warning("    PSF files are found in $DESIMODEL")
        log.warning("    Templates are read from $DESI_BASIS_TEMPLATES")

    #- Wait until end to raise exception so that we report everything that
    #- is missing before actually failing
    if missing_env:
        log.critical("missing env vars; exiting without running simulations or quicklook pipeline")
        sys.exit(1)

#- Default values for all arguments unless told otherwise 
def parse(options=None):
    """
    Can change night or number of spectra to be simulated and delete all output of test

    Won't overwrite exisiting data unless overwrite argument provided

    Quicklook output can be written to $QL_SPECPROD if specified
    """
    parser=argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--night',type=str,default='20160728',help='night to be simulated')
    parser.add_argument('--nspec',type=int,default=5,help='number of spectra to be simulated, starting from first')
    parser.add_argument('--overwrite', action='store_true', help='overwrite existing files')
    parser.add_argument('--delete', action='store_true', help='delete all files generated by this test')
    parser.add_argument('--ql_specprod', action='store_true', help='write output to $QL_SPECPROD instead of $SPECPROD')

    if options is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(options)

    log = logging.get_logger()
    log.setLevel(logging.DEBUG)

    # Include $QL_SPECPROD vs. $SPECPROD variable check here since it can be given as keyword
    missing_env = False
    if args.ql_specprod:
        if 'QL_SPECPROD' not in os.environ:
            log.warning("missing ${}".format('QL_SPECPROD'))
            missing_env = True
    else:
        if 'SPECPROD' not in os.environ:
            log.warning("missing ${}".format('SPECPROD'))
            missing_env = True

    if missing_env:
        log.warning("Why are these needed?")
        log.warning("    Output written to either $DESI_SPECTRO_REDUX/$SPECPROD or $DESI_SPECTRO_REDUX/$QL_SPECPROD")

    sim_dir = os.path.join(os.environ['DESI_SPECTRO_SIM'],os.environ['PIXPROD'],args.night)
    data_dir = os.path.join(os.environ['DESI_SPECTRO_DATA'],os.environ['PIXPROD'],args.night)
    if args.ql_specprod:
        output_dir = os.path.join(os.environ['DESI_SPECTRO_REDUX'],os.environ['QL_SPECPROD'])
    else:
        output_dir = os.path.join(os.environ['DESI_SPECTRO_REDUX'],'QL',os.environ['SPECPROD'])

    if args.overwrite:
        if os.path.exists(sim_dir):
            sim_files = os.listdir(sim_dir)
            for file in range(len(sim_files)):
                sim_file = os.path.join(sim_dir,sim_files[file])
                os.remove(sim_file)
            os.rmdir(sim_dir)
        if os.path.exists(data_dir):
            data_files = os.listdir(data_dir)
            for file in range(len(data_files)):
                data_file = os.path.join(data_dir,data_files[file])
                os.remove(data_file)
            os.rmdir(data_dir)
        if os.path.exists(output_dir):
            exp_dir = os.path.join(output_dir,'exposures',args.night)
            calib_dir = os.path.join(output_dir,'calib2d',args.night)
            if os.path.exists(exp_dir):
                id_dir = os.path.join(exp_dir,'00000002')
                if os.path.exists(id_dir):
                    id_files = os.listdir(id_dir)
                    for file in range(len(id_files)):
                        id_file = os.path.join(id_dir,id_files[file])
                        os.remove(id_file)
                    os.rmdir(id_dir)
                exp_files = os.listdir(exp_dir)
                for file in range(len(exp_files)):
                    exp_file = os.path.join(exp_dir,exp_files[file])
                    os.remove(exp_file)
                os.rmdir(exp_dir)
            if os.path.exists(calib_dir):
                calib_files = os.listdir(calib_dir)
                for file in range(len(calib_files)):
                    calib_file = os.path.join(calib_dir,calib_files[file])
                    os.remove(calib_file)
                os.rmdir(calib_dir)            

    else:
        if os.path.exists(sim_dir) or os.path.exists(data_dir) or os.path.exists(output_dir):
            raise RuntimeError('Files already exist for this night! Can overwrite or change night if necessary')

    return args

def sim(night, nspec, ql_specprod):
    """
    Simulate data as part of the quicklook integration test.

    Args:
        night (str): YEARMMDD
        nspec (int): number of spectra to include
        ql_specprod: output sent to $QL_SPECPROD if specified
 
    Raises:
        RuntimeError if any script fails
    """

#    psf_b = os.path.join(os.environ['DESIMODEL'],'data','specpsf','psf-b.fits')
    psf_r = os.path.join(os.environ['DESIMODEL'],'data','specpsf','psf-r.fits')
    psf_z = os.path.join(os.environ['DESIMODEL'],'data','specpsf','psf-z.fits')

    # Create files needed to run quicklook

    sim_dir = os.path.join(os.environ['DESI_SPECTRO_SIM'],os.environ['PIXPROD'],night)
    data_dir = os.path.join(os.environ['DESI_SPECTRO_DATA'],os.environ['PIXPROD'],night)
    if ql_specprod == 'Use $QL_SPECPROD':
        output_dir = os.path.join(os.environ['DESI_SPECTRO_REDUX'],os.environ['QL_SPECPROD'])
    else:
        output_dir = os.path.join(os.environ['DESI_SPECTRO_REDUX'],'QL',os.environ['SPECPROD'])
    exp_dir = os.path.join(output_dir,'exposures',night)
    calib_dir = os.path.join(output_dir,'calib2d',night)

    for expid, flavor in zip([0,1,2], ['arc', 'flat', 'dark']):

        cmd = "newexp-desi --flavor {} --nspec {} --night {} --expid {}".format(flavor,nspec,night,expid)
        if runcmd(cmd) != 0:
            raise RuntimeError('newexp failed for {} exposure {}'.format(flavor, expid))

        if flavor == 'dark':
            cmd = "pixsim-desi --night {} --expid {} --nspec {} --rawfile {}/desi-{:08d}.fits.fz".format(night,expid,nspec,data_dir,expid)
            if runcmd(cmd) != 0:
                raise RuntimeError('pixsim failed for {} exposure {}'.format(flavor, expid))

        if flavor == 'arc' or flavor == 'flat':
            cmd = "pixsim-desi --night {} --expid {} --nspec {} --rawfile {}/desi-{:08d}.fits.fz --preproc --preproc_dir {}".format(night,expid,nspec,data_dir,expid,data_dir)
            if runcmd(cmd) != 0:
                raise RuntimeError('pixsim failed for {} exposure {}'.format(flavor, expid))

        if flavor == 'flat':

#            cmd = "desi_extract_spectra -i {}/pix-b0-00000001.fits -o {}/{}/frame-b0-00000001.fits -f {}/fibermap-00000001.fits -p {} -w 3550,5730,0.8 -n {}".format(data_dir,exp_dir,sim_dir,psf_b,nspec)
#            if runcmd(cmd) != 0:
#                raise RuntimeError('desi_extract_spectra failed for camera b0')

            cmd = "desi_extract_spectra -i {}/pix-r0-00000001.fits -o {}/frame-r0-00000001.fits -f {}/fibermap-00000001.fits -p {} -w 5630,7740,0.8 -n {}".format(data_dir,exp_dir,sim_dir,psf_r,nspec)
            if runcmd(cmd) != 0:
                raise RuntimeError('desi_extract_spectra failed for camera r0')

            cmd = "desi_extract_spectra -i {}/pix-z0-00000001.fits -o {}/frame-z0-00000001.fits -f {}/fibermap-00000001.fits -p {} -w 7650,9830,0.8 -n {}".format(data_dir,exp_dir,sim_dir,psf_z,nspec)
            if runcmd(cmd) != 0:
                raise RuntimeError('desi_extract_spectra failed for camera z0')

        os.rename(os.path.join(sim_dir,'fibermap-{:08d}.fits'.format(expid)),os.path.join(data_dir,'fibermap-{:08d}.fits'.format(expid)))
        os.remove(os.path.join(data_dir,'simpix-{:08d}.fits'.format(expid)))

    for camera in ['r0','z0']:

        cmd = "desi_compute_fiberflat --infile {}/frame-{}-00000001.fits --outfile {}/fiberflat-{}-00000001.fits".format(exp_dir,camera,calib_dir,camera)
        if runcmd(cmd) != 0:
            raise RuntimeError('desi_compute_fiberflat failed for camera {}'.format(camera))

        cmd = "desi_bootcalib --fiberflat {}/pix-{}-00000001.fits --arcfile {}/pix-{}-00000000.fits --outfile {}/psfboot-{}.fits".format(data_dir,camera,data_dir,camera,calib_dir,camera)
        if runcmd(cmd) != 0:
            raise RuntimeError('desi_bootcalib failed for camera {}'.format(camera))

    return

def integration_test(args=None):
    """Run an integration test from raw data simulations through quicklook pipeline

    Args:
        night (str): YEARMMDD
        nspec (int): number of spectra to include
        clobber (bool, optional): rerun steps even if outputs already exist

    Raises:
        RuntimeError if quicklook fails
    """

    args = parse(args)

    night = args.night
    nspec = args.nspec
    expid = 2
    flat_expid = 1

    raw_dir = os.path.join(os.environ['DESI_SPECTRO_DATA'],os.environ['PIXPROD'])
    if args.ql_specprod:
        ql_specprod = 'Use $QL_SPECPROD'
        output_dir = os.path.join(os.environ['DESI_SPECTRO_REDUX'],os.environ['QL_SPECPROD'])
    else:
        ql_specprod = 'Use $SPECPROD'
        output_dir = os.path.join(os.environ['DESI_SPECTRO_REDUX'],'QL',os.environ['SPECPROD'])
    calib_dir = os.path.join(output_dir,'calib2d',night)

    # check for required environment variables and simulate inputs
    check_env()
    sim(night=night, nspec=nspec, ql_specprod=ql_specprod)

    for camera in ['r0','z0']:

        # find all necessary input and output files
        psffile = os.path.join(calib_dir,'psfboot-{}.fits'.format(camera))
        fiberflatfile = os.path.join(calib_dir,'fiberflat-{}-{:08d}.fits'.format(camera,flat_expid))

        # verify that quicklook pipeline runs
        com = "desi_quicklook -n {} -c {} -e {} -f {} --psfboot {} --fiberflat {} --rawdata_dir {} --specprod_dir {}".format(night,camera,expid,'dark',psffile,fiberflatfile,raw_dir,output_dir)
        if runcmd(com) != 0:
            raise RuntimeError('quicklook pipeline failed for camera {}'.format(camera))

        # lastframe files are output to current working directory
        # should fix this, but will delete this file for now
        os.remove('lastframe-{}-{:08d}.fits'.format(camera,expid))

    # remove all output if desired
    if args.delete:
        sim_dir = os.path.join(os.environ['DESI_SPECTRO_SIM'],os.environ['PIXPROD'],args.night)
        if os.path.exists(sim_dir):
            sim_files = os.listdir(sim_dir)
            for file in range(len(sim_files)):
                sim_file = os.path.join(sim_dir,sim_files[file])
                os.remove(sim_file)
            os.rmdir(sim_dir)
        data_dir = os.path.join(raw_dir,night)
        if os.path.exists(data_dir):
            data_files = os.listdir(data_dir)
            for file in range(len(data_files)):
                data_file = os.path.join(data_dir,data_files[file])
                os.remove(data_file)
            os.rmdir(data_dir)
        if os.path.exists(output_dir):
            exp_dir = os.path.join(output_dir,'exposures',night)
            if os.path.exists(exp_dir):
                id_dir = os.path.join(exp_dir,'00000002')
                if os.path.exists(id_dir):
                    id_files = os.listdir(id_dir)
                    for file in range(len(id_files)):
                        id_file = os.path.join(id_dir,id_files[file])
                        os.remove(id_file)
                    os.rmdir(id_dir)
                exp_files = os.listdir(exp_dir)
                for file in range(len(exp_files)):
                    exp_file = os.path.join(exp_dir,exp_files[file])
                    os.remove(exp_file)
                os.rmdir(exp_dir)
            if os.path.exists(calib_dir):
                calib_files = os.listdir(calib_dir)
                for file in range(len(calib_files)):
                    calib_file = os.path.join(calib_dir,calib_files[file])
                    os.remove(calib_file)
                os.rmdir(calib_dir)

if __name__ == '__main__':
    integration_test()

