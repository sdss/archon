
archon's documentation
======================

This is the documentation for the SDSS Python product archon. The current version is |archon_version|. You can install the package by doing

.. code-block:: console

  $ pip install sdss-archon

Refer to the `repository <https://github.com/sdss/archon>`__ for details on how to develop the code and for issue tracking.

Getting started
---------------

The ``archon`` product provides a `wrapper <.ArchonController>` for the `STA Archon <http://www.sta-inc.net/archon/>`__ controller and exposes the controller features as an `~clu.actor.AMQPActor`. Note that this library uses `asyncio` throughout the codebase to enable asynchronicity.

`.ArchonController` provides a mid-level interface to the Archon controller and implements the protocol for communicating with the controller. ::

  >>> from archon.controller import ArchonController
  >>> archon = ArchonController('10.7.45.25')
  >>> archon
  <archon.controller.controller.ArchonController at 0x7f5de43d3ee0>
  >>> await archon.start()
  >>> cmd = archon.send_command('SYSTEM')
  >>> cmd
  <ArchonCommand (>01SYSTEM, status=ArchonCommandStatus.RUNNING)>
  >>> await cmd
  >>> cmd
  <ArchonCommand (>00SYSTEM, status=ArchonCommandStatus.DONE)>
  >>> cmd.replies
  [<ArchonCommandReply (b'<01BACKPLANE_TYPE=1 BACKPLANE_REV=5 BACKPLANE_VERSION=1.0.1104 BACKPLANE_ID=00003FFF1A9902F6 POWER_ID=0000014A46C4 MOD_PRESENT=FFF MOD1_TYPE=12 MOD1_REV=2 MOD1_VERSION=1.0.1104 MOD1_ID=013C82C81218EAC1 MOD2_TYPE=11 MOD2_REV=0 MOD2_VERSION=1.0.1104 MOD2_ID=013ADF5CE983EED1 MOD3_TYPE=16 MOD3_REV=0 MOD3_VERSION=1.0.1104 MOD3_ID=013F0B0C2B9A098A MOD4_TYPE=9 MOD4_REV=0 MOD4_VERSION=1.0.1104 MOD4_ID=013BDC58A3770501 MOD5_TYPE=2 MOD5_REV=10 MOD5_VERSION=1.0.1104 MOD5_ID=013CA1A7F8456290 MOD6_TYPE=2 MOD6_REV=10 MOD6_VERSION=1.0.1104 MOD6_ID=0135E6C7132CAB69 MOD7_TYPE=2 MOD7_REV=10 MOD7_VERSION=1.0.1104 MOD7_ID=013D20299487C81A MOD8_TYPE=16 MOD8_REV=0 MOD8_VERSION=1.0.1104 MOD8_ID=013C005A12A71540 MOD9_TYPE=8 MOD9_REV=0 MOD9_VERSION=1.0.1104 MOD9_ID=013FC3304C7B3552 MOD10_TYPE=16 MOD10_REV=0 MOD10_VERSION=1.0.1104 MOD10_ID=013613E28D6F9CFA MOD11_TYPE=16 MOD11_REV=0 MOD11_VERSION=1.0.1104 MOD11_ID=013AC627F3458711 MOD12_TYPE=11 MOD12_REV=0 MOD12_VERSION=1.0.1104 MOD12_ID=013F95EDEF775096 \n')>]

`~.ArchonController.send_command` allows to send a raw command to the controller, while managing command IDs, message formatting, and reply parsing. `~.ArchonController.send_command` returns a `.ArchonCommand`, which is a `~asyncio.Future` that can e awaited until the Archon command completes or fails. The replies from the controller are stored in `.ArchonCommand.replies` as a list of `.ArchonCommandReply`.

`.ArchonController` also provides some mid-level routines to automate complex processes such as `loading a configuration file <.ArchonController.read_config>`, retrieving the `controller status <.ArchonController.get_device_status>`, `integrating <.ArchonController.expose>`, `fetching the buffer <.ArchonController.fetch>`, etc. Refer to the API documentation for a list of methods.

The controller object tracks its internal status via the `.ArchonController.status` attribute, which is always one of `.ControllerStatus`. It's possible to "subscribe" to the controller status via the `~.ArchonController.get_device_status` asynchronous generator.

Actor
^^^^^

The actor functionality is a relatively straightforward implementation of the `~clu.actor.AMQPActor` `CLU <https://clu.readthedocs.io/en/latest/>`__ actor and we refer you to the documentation therein.

`.ArchonActor` is instantiated as any `~clu.actor.AMQPActor` but a list of `.ArchonController` instances must also be passed, indicating the Archon devices with which the actor will interface. Normally this information is encoded in a configuration file that is passed to `~.ArchonActor.from_config`, which returns a new instance of `.ArchonActor` with the controllers already loaded. For an example of a configuration file see `this file <https://github.com/sdss/archon/blob/main/archon/etc/archon.yml>`__.

A list of available actor commands is described :ref:`here <actor-commands>` and can also be output using the actor command ``help``. The JSONSchema of the actor replies can be consulted :ref:`here <actor-schema>`.

A simple CLI interface is provided to run the actor.

.. code-block:: console

  $ archon --help
  Usage: archon [OPTIONS] COMMAND [ARGS]...

    Archon controller

  Options:
    -c, --config FILE  Path to the user configuration file.
    -v, --verbose      Debug mode. Use additional v for more details.
    --help             Show this message and exit.

  Commands:
    actor*  Runs the actor.

To start the actor in detached (daemon) mode run ``archon actor start``. This is roughly equivalent to the following script ::

  archon_actor = ArchonActor.from_config(config_file)
  await archon_actor.start()
  await archon_actor.run_forever()

Use the flag ``--debug`` with ``archon actor start`` to prevent the process from detaching, which is useful for development and debugging.

Docker
^^^^^^

The product is automatically built into a Docker image, which is pushed to the SDSS GitHub Container Registry `ghcr.io/sdss/archon <https://github.com/orgs/sdss/packages/container/package/archon>`__. New commits to the ``main`` branch are tagged as ``latest`` in the image, while git tags are tagged with the same version number. The Dockerfile is linked `here <https://github.com/sdss/archon/blob/main/Dockerfile>`__. The default entrypoint to the container will run the actor.

To run the actor as a Docker container (for production, replace ``latest`` with the desired tag):

.. code-block:: console

  $ docker pull ghcr.io/sdss/archon:latest
  latest: Pulling from ghcr.io/sdss/archon
  5d3b2c2d21bb: Pull complete
  3fc2062ea667: Pull complete
  75adf526d75b: Pull complete
  008b9e4aa9fb: Pull complete
  6e2be73a0b44: Pull complete
  271dfd2e19e9: Pull complete
  7c98efabc49f: Pull complete
  da2e0799db78: Pull complete
  Digest: sha256:a797ebd6dde34098e8ae1e1a26a067a8211192bdc845e9f3fc576074447c2bf4
  Status: Downloaded newer image for ghcr.io/sdss/archon:latest

  $ docker run --name archon --rm --detach --network host ghcr.io/sdss/archon:latest
  32081bdb47b67de65e77d3f1e720da1fc642f650c4441108c4a7f26e131e8f10

The container needs access to the host network to connect to the Archon controller(s) (usually on port 4242) and to the RabbitMQ instance (usually on port 5672). There are different ways to accomplish that (see the documentation for `Bridge networking <https://docs.docker.com/network/bridge/>`__ and `this thread <https://forums.docker.com/t/accessing-host-machine-from-within-docker-container/14248>`__) but the easiest one is to use the `host network <https://docs.docker.com/network/host/>`__ by passing ``--network host`` as we did above. Note that this breaks the isolation of the container in ways that may be unsafe.


.. toctree::
  :caption: Reference
  :maxdepth: 3
  :hidden:

  api
  actor-commands
  actor-schema

.. toctree::
  :caption: Development
  :maxdepth: 3
  :hidden:

  Changelog <changelog>
  GitHub Repository <https://github.com/sdss/archon>
  Issues  <https://github.com/sdss/archon/issues>
