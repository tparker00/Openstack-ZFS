Openstack-ZFS
=============

zfs plugin for Cinder in openstack Folsom

Based off of work from David Douard in the following blog post. http://www.logilab.org/blogentry/114769

To install copy zol.py to /usr/share/pyshared/cinder/volume and make the following changes to /etc/cinder/cinder.conf

volume\_driver=cinder.volume.zol.ZFSonLinuxISCSIDriver  
volume\_group=\<zvol\_path\>  
iscsi\_ip\_prefix=\<ip\_prefix\>  
iscsi\_ip\_address=\<cinder\_ip\>  
san\_thin\_provision=false  
san\_ip=\<cinder\_ip\>  
san\_zfs\_volume\_base=\<zvol\_path\>  
san\_is\_local=true  
use\_cow\_images=false
