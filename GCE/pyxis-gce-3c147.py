from Pyxis.ModSupport import *

gc = x.gcloud

SNAPSHOT = "oms-papino-3"
VMNAME = "oms-1"
DISKSIZE = 200
VMTYPE = "n1-standard-1"

## create VM
def init_vm (vmname="$VMNAME",disksize="$DISKSIZE",vmtype="$VMTYPE"):
  """Creates a GCE VM instance""";
  name,disksize,vmtype = interpolate_locals("vmname disksize vmtype");
  gc("compute disks create $name --source-snapshot $SNAPSHOT")
  gc("compute disks create ${name}-data --size $disksize"); 
  gc("""compute instances create $name --machine-type n1-standard-1 --disk name=$name mode=rw boot=yes auto-delete=yes --disk name=${name}-data mode=rw""");
  info("created VM instance $name, type $vmtype, data disk of size $disksize")
  return name;

def delete_vm (vmname="$VMNAME",keepdata=False):
  """Deletes a GCE VM instance""";
  name = interpolate_locals("vmname")
  gc("compute instances delete $name --quiet");
  info("deleted VM instance $name");
  if keepdata:
    info("keepdata=True, preserving data disk ${name}-data")
  else:
    gc("compute disks delete ${name}-data --quiet");
    info("deleted VM data dist ${name}-data");

def provision_data (vmname="$VMNAME"):
  """Provision a GCE VM instance""";
  name = interpolate_locals("vmname")
  gc("compute ssh $name --command 'sudo mkdir /data'");
  gc("compute ssh $name --command 'sudo chown $USER.$USER /data'");
  gc("compute ssh $name --command 'sudo /usr/share/google/safe_format_and_mount -m \"mkfs.ext4 -F\" /dev/sdb /data'");
  gc("compute ssh $name --command 'ln -s /data'");

def provision (vmname="$VMNAME"):
  """Provision a GCE VM instance""";
  name = interpolate_locals("vmname")
  gc("ssh $name sudo mkdir /data");
  gc("ssh $name sudo chown $USER.$USER /data");
  gc("ssh $name sudo /usr/share/google/safe_format_and_mount -m 'mkfs.ext4 -F' /dev/sdb /data");
  gc("ssh ln -s /data");


