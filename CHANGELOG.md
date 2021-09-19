# Changelog

## Next release

### ✨ Improved

* [#32](https://github.com/sdss/archon/issues/32) Expand the default header with information about gain, readout noise, bias section, etc.
* [#24](https://github.com/sdss/archon/issues/24) Added `ExposureDelegate.readout_cotasks()` that can be overridden to execute tasks concurrently during readout. The LVM delegate now reads temperatures and IEB data at this point.
* [#34](https://github.com/sdss/archon/issues/34) The path to the last ACF file written to the controller is stored in the user configuration file (usually at `~/.config/sdss/archon.yaml`) from where it's read when the controller starts. This prevents having to initialise the controller every time `archon` is restarted (with the corresponding power cycling of the CCDs) just to update the ACF path, but it introduces a certain risk that the ACF stored in the configuration file and the one loaded are actually different. In general it's still recommended to do an `archon init` when the daemon is restarted.
* Added script for ~800MHz readout.
* Use `framemode=split` and rearrange taplines to allow proper display in the GUI.


## 0.5.0 - September 6, 2021

### 🚀 New

* [#29](https://github.com/sdss/archon/pull/29) Support binning.
* [#30](https://github.com/sdss/archon/pull/30) HDR (32-bit sampling) mode can be enabled when loading the script by running `archon init --hdr [<script>]`.

### ✨ Improved

* `archon init` accepts an optional parameter to define the ACF script to load.
* [#31](https://github.com/sdss/archon/pull/31) Tests for the actor.

### 🔧 Fixed

* Fixed error when moving shutter or hartmann doors manually.


## 0.4.0 - August 22, 2021

### 🚀 New

* Added `--count` flag to `lvm expose` to support multiple consecutive exposures.
* Support for the three LVM CCDs.

### ✨ Improved

* Always close connections to remote TCP services to prevent leaving unclosed file descriptors.
* Read pressure sensors concurrently.
* Update LVM lamps.

### 🔧 Fixed

* Improve how auto-flushing is implemented. In its previous mode, `FlushOne` would often be called once between exposing and reading out, introducing an offset in the lines that manifested as a lines overscan of ~90 lines. The new implementation allows to disable auto-flushing before an exposure begins.


## 0.3.0 - June 20, 2021

### 🚀 New

* [#21](https://github.com/sdss/archon/pull/21) Implemented profiles for LVM and BOSS (placeholder).
* [#22](https://github.com/sdss/archon/pull/22) Implement custom LVM expose delegate along with a group of `lvm` commands to control the shutter, hartmann doors, and to expose using the shutter.
* [#23](https://github.com/sdss/archon/pull/23) Refactor expose actor code into an `ExposeDelegate` that allows for more flexible customisation.
* [#26](https://github.com/sdss/archon/pull/26) Use the [furo](https://pradyunsg.me/furo/) theme for the documentation.
* Add option to define additional header keywords in the configuration file that read values from the actor keyword datamodel.
* Add `lvm-lab` script for laboratory testing.
* `POWERON` and `POWERBAD` controller status bits.
* Code to log LVM exposures in Google Sheets.

### 🔧 Fixed

* Require `sdss-clu>=0.7.8` to allow `archon expose finish --header` to work with strings that have spaces. It should now be possible to pass commands like `archon expose finish --header '{"KEYWORD1": [1, "A comment"]}'`. For header keyword values that are a list of value and comment, the list is converted into a tuple internally so that `astropy` can parse it correctly.

### 🧹 Cleanup

* [#17](https://github.com/sdss/archon/issues/17) Handle actor shutdown more gently when it is started from the CLI either in debug mode or as a daemon.


## 0.2.1 - April 6, 2021

### 🔧 Fixed

* Fix Docker creation for tags.


## 0.2.0 - April 6, 2021

### 🚀 New

* [#10](https://github.com/sdss/archon/issues/10) Add actor command `reconnect` that allows to recreate the TCP/IP connection to one or multiple controllers. If the controller cannot be connected when the actor starts, a warning is issued but the actor will be created.
* [#11](https://github.com/sdss/archon/issues/11) Read the Govee H5179 temperature and humidity and write a basic FITS header.
* [#12](https://github.com/sdss/archon/issues/12) Add `ArchonController` methods to `abort`, `read out`, and `flush` an exposure. Actor `expose` command now accepts `expose start` and `expose finish` to allow for non-blocking integration. Better handling of status flags.

### 🧹 Cleanup

* Basic documentation.
* Use GitHub Container Registry instead of Docker Hub.


## 0.1.0 - March 6, 2021

### 🚀 New

* Initial version of the library and actor. Supports communication with the Archon controller, Archon command tracking and reply parsing, and basic actor functionality, including exposing.
* Build and push docker image to [lvmi/archon](https://hub.docker.com/repository/docker/lvmi/archon).
