# Building and Development
Phoenix is written in Python, so there is not really anything to build. The developers recommend assembling Phoenix into a system package so that CLIs show up in the default path and daemons register with systemd.

{: .notice--warning}
**Note:** Most people should be fine to use the pre-built system packages provided.

## Building Phoenix as a RPM
From the git checkout, run:

	python3 setup.py bdist_rpm
	
{: .notice--danger}
**Warning:** This method does not allow for much customization, and it is not well-supported upstream. Phoenix will be moving to a spec file with a helper script in upcoming releases.

## Building Phoenix as a DEB
Phoenix has not been tested on Debian or Ubuntu. Please reach out to the developers if you have any interest!

## Running Phoenix from a git checkout
For development, it is easier to use a local checkout than building an RPM.  If you checkout the repo at `$HOME/phoenix`, setup the following environment:

	export PATH=$PATH:$HOME/phoenix/bin
	export PYTHONPATH=$HOME/phoenix/lib
	export PHOENIX_CONF=$HOME/phoenix/conf

If you've never installed the RPM, manually install some dependencies:

    sudo dnf -y install clustershell python3-jinja2

## Running Tests
A test framework for Phoenix has not yet been developed. If you have ideas or cycles to spare, please reach out to the developers!

## Reporting Issues and Pull Requests
Currently the main issue tracker for Phoenix is hosted in a private repository. If there is enough interest, it can be migrated to GitHub. Feel free to open new [issues](https://github.com/olcf/phoenix/issues) or [pull requests](https://github.com/olcf/phoenix/pulls) in GitHub or contact the developers directly.
