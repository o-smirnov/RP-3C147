from Pyxis.ModSupport import *

import socket
import glob
import time
import os.path

define('PROJECT',"meerkat-7-gazing","default GCE project name")
define('COMPZONE',"europe-west1-a","default GCE compute zone")

# gcloud executable
# includes PROJECT and COMPZONE in the command line
gc = x.gcloud.args(before="compute --project $PROJECT",after="--zone $COMPZONE");
gco = xo.gcloud.args(before="compute --project $PROJECT",after="--zone $COMPZONE");
gcr = xr.gcloud.args(before="compute --project $PROJECT",after="--zone $COMPZONE");
gcro = xro.gcloud.args(before="compute --project $PROJECT",after="--zone $COMPZONE");

define('SNAPSHOT',"oms-papino-5","snapshot on which boot disk is to be based")
define('DATADISKSIZE',200,"default data disk size (in Gb) for VM instances")
define('VMTYPE',"n1-standard-1","default VM type")

define("VMNUM",1,"VM serial number")
define('VMNAME_Template',"${USER}-"+socket.gethostname().replace(".","-").lower()+"-$VMNUM","default VM name")

define('USER',E.USER,"default username to be used on remote machine")

def _remote_provision ():
  for repo in ("pyxis","meqtrees-cattery"):
    if os.path.exists(repo):
      x.sh("git -C $repo pull");
  info("VM provision complete");

## create VM
def init_vm (vmname="$VMNAME",vmtype="$VMTYPE",reuse_boot=True,provision=True):
  """Creates a GCE VM instance""";
  name,vmtype = interpolate_locals("vmname vmtype");
  # check if a boot disk needs to be created
  disks = get_disks();
  if name in disks:
    if reuse_boot:
      info("boot disk $name already exists and reuse_boot=True")
    else:
      gc("disks delete $name --quiet")
      del disks[name];
  if name not in disks:
    gc("disks create $name --source-snapshot $SNAPSHOT")
  # create VM
  gc("instances create $name --machine-type n1-standard-1 --disk name=$name mode=rw boot=yes auto-delete=yes");
  info("created VM instance $name, type $vmtype")
  # provision with pyxis scripts in current directory
  if provision:
    provision_vm(name);

def provision_vm (vmname="$VMNAME"):
  name = interpolate_locals("vmname");
  # make sure the machine is ready -- retry the file copy until we succeed
  files = " ".join(list(glob.glob("pyxis-*py")) + list(glob.glob("pyxis-*.conf")));
  for attempt in range(1,11):
    if gco("copy-files $files $name:",quiet=True) is 0:
      break;
    if attempt is 1 and name not in get_vms():
      abort("no such VM $name")
    warn("VM $name is not up yet (attempt #$attempt), waiting for 10 seconds and retrying");
    time.sleep(10);
  else:
    abort("failed to connect to VM $name after $attempt tries")
  info("copied $files to VM, running provisioning command");
  gc("ssh $name --command 'pyxis _remote_provision'")


def _remote_attach_disk (diskname,mount,clear):
  if not os.path.exists(mount):
    x.sh("sudo mkdir $mount");
  x.sh("sudo /usr/share/google/safe_format_and_mount -m 'mkfs.ext4 -F' /dev/disk/by-id/google-$diskname $mount");
  x.sh("sudo chown $USER.$USER $mount");
  if clear:
    x.sh("sudo rm -fr $mount/*");
  # make symlink, if mounting at root level 
  mm = os.path.realpath(mount).split("/");
  if len(mm) < 3 and not os.path.exists(mm[-1]):
    gc("ln -s $mount");

def attach_disk (vmname="$VMNAME",diskname="${vmname}-$mount",size="$DATADISKSIZE",
                 mount="/data",ssd=False,
                 init=False,clear=False,mode="rw",autodelete=False):
  name,diskname,disksize,mount = interpolate_locals("vmname diskname size mount")
  diskname = diskname.lower().replace("/","");
  disks = get_disks();
  if diskname in disks and init:
    info("disk $diskname exists and init=True, recreating")
    gc("disks delete $diskname");
    del disks[diskname];
  if diskname not in disks:
    disktype = "pd-ssd" if ssd else "pd-standard";
    info("disk $diskname does not exist, creating type $disktype, size $disksize Gb")
    gc("disks create $diskname --size $disksize --type $disktype")
    clear = False;
  # attach disk to VM
  gc("instances attach-disk $name --disk $diskname --mode $mode --device-name $diskname")
  if autodelete:
    gc("instances set-disk-auto-delete --auto-delete $name --disk $diskname")
  # execute rest on remote
  gc("ssh $name --command 'pyxis _remote_attach_disk[$diskname,$mount,$clear]'");
  # 
  info("attached disk $diskname as $name:$mount ($mode)")


def detach_disk (vmname="$VMNAME",diskname="${vmname}-data"):
  name,diskname = interpolate_locals("vmname diskname")
  gc("instances detach-disk $name --disk $diskname")
  info("detached disk $diskname from VM $name")


def get_vms ():
  return dict([ x.split(None,1) for x in gcr("instances list").split("\n")[1:] if x])

def get_disks ():
  return dict([ x.split(None,1) for x in gcr("disks list").split("\n")[1:] if x])

def delete_disk (*disknames):
  for disk in disknames:
    gc("disks delete $disk --quiet");

def delete_vm (vmname="$VMNAME"):
  """Deletes a GCE VM instance""";
  name = interpolate_locals("vmname");
  gc("instances delete $name --quiet");
  info("deleted VM instance $name");

