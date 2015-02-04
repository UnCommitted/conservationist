conservationist
===============

Manages environments and submodules in puppet > 3.6.5

## Usage

Run `culivate -h` for all options

```bash
usage: cultivate [-h] [--puppetdir PUPPETDIR] [--hieradir HIERADIR]
                 {report,migrate} ...

optional arguments:
  -h, --help            show this help message and exit
  --puppetdir PUPPETDIR
                        Root of the puppet configuration repositoryDefaults to
                        /etc/puppet
  --hieradir HIERADIR   Path to hiera data. Defaults to hiera. If the path
                        starts with a / it is an absolute path,otherwise a
                        path relative to the puppetdir

subcommands:
  valid subcommands

  {report,migrate}      additional help
    report              Print report of the given repo.
    migrate             Migrate configuration between puppet environments.
```

### Migrations

```bash
usage: cultivate migrate [-h] [--from_env FROM_ENV] [--to_env TO_ENV]

optional arguments:
  -h, --help           show this help message and exit
  --from_env FROM_ENV  Default: dev
  --to_env TO_ENV      Default: production
```
