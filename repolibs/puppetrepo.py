"""
Puppet Repository related objects
"""
import os
import re
import sys
from subprocess import *
from .gitrepo import GitRepo, GitRepoError

class PuppetConfigRepoError(Exception):
    """
    Raised when a repository root can't be found
    """
    def __init__(self, message):
        """
        Print out the error message
        """
        super().__init__()
        self.message = message

    def __str__(self):
        """
        String Representation of this object
        """
        return self.message

class PuppetEnvironmentError(PuppetConfigRepoError):
    """
    Raised on issues with a Puppet Environment
    """

class PuppetModuleError(PuppetConfigRepoError):
    """
    Raised on issues with a Puppet Module
    """

class PuppetModule(object):
    """
    Representation of a puppet module within an environment
    """

    # Class regular expression for finding the shasum of a commit
    findsha = re.compile(r'^(?P<shasum>.*?)\s+')

    def __init__(self, module_root):
        """
        Set up a representation of this module
        NOTE: Module root MUST be a full path
        """
        if not os.path.isdir(module_root):
            raise PuppetModuleError(module_root + 'is not a directory')

        self.module_root = module_root
        self.module_name = os.path.basename(module_root)

        # Check if we are a git submodule
        self.is_submodule = os.path.isfile(module_root + '/.git')

        if self.is_submodule:
            self.commit = self.get_commit()
        else:
            self.commit = None

    def get_commit(self):
        """
        Returns the sha1sum of the commit our module is at
        """
        tempdir = os.getcwd()
        os.chdir(self.module_root)

        try:
            # Run the git show command
            commit = Popen(['git', 'show', '--pretty=oneline'], stdout=PIPE)
            stdout = commit.communicate()[0]

            # Parse each line of the file, and add the module_path
            # to the corresponding environment
            line = stdout.decode('utf-8')
            matches = PuppetModule.findsha.search(line)
            shasum = None
            if matches:
                shasum = matches.group('shasum')

            # Change back to our original directory
            os.chdir(tempdir)
            return shasum

        except CalledProcessError:
            os.chdir(tempdir)
            sys.stderr.write("Unable to get module commit shasum\n")
            sys.exit(1)

    def __str__(self):
        """
        String representation of a PuppetModule
        """
        representation = '    Module Name: ' + self.module_name + "\n"
        representation +=\
            '        Module Root : ' + self.module_root + "\n"
        representation +=\
            '        Is submodule: '\
            + str(self.is_submodule)\
            + "\n"

        representation += '        Commit      : ' + str(self.commit) + "\n"
        return representation


class PuppetConfigRepo(object):
    """
    Representation of a puppet configuration directory
    structure.
    """

    def __init__(self, repo_root, hiera_root):
        """
        Create an object representing the Puppet
        configuration directory.

        repo_root should be a full path
        hiera_root should be a full path
        """
        # Check that the paths exist
        if not os.path.isdir(repo_root):
            raise PuppetConfigRepoError(repo_root + 'is not a directory')

        if not os.path.isdir(hiera_root):
            raise PuppetConfigRepoError(hiera_root + 'is not a directory')

        self.starting_dir = os.getcwd()
        self.repo_root = repo_root
        self.hiera_root = hiera_root

        # See if we are inside a git repo.
        try:
            self.gitrepo = GitRepo(self.repo_root)
        except GitRepoError:
            # We are not in a git repository for some reason
            self.gitrepo = None

        self.environments = self.find_environments()

    def env_names(self):
        """
        Returns a list of names of the environments in the puppet repository
        """
        return self.environments.keys()

    def migrate(self, from_env, to_env):
        """
        Migrate data between 2 environments
        """
        # Check that the environments and hieradata actually exist
        for env in [from_env, to_env]:
            if not env in self.environments:
                raise PuppetConfigRepoError(
                    '{} environment does not exist'.format(env)
                )

        from_hiera = '{}/environments/{}'.format(self.hiera_root, from_env)
        to_hiera = '{}/environments/{}'.format(self.hiera_root, to_env)

        for hiera_dir in [from_hiera, to_hiera]:
            if not os.path.isdir(hiera_dir):
                raise PuppetConfigRepoError(
                    '{} is not a directory'.\
                    format(hiera_dir)
                )

        # Create a comparison between environments to check that we can
        # migrate.
        tempcomparison = PuppetEnvComparison(
            self.environments[from_env],
            self.environments[to_env]
        )

        if not tempcomparison.is_migratable():
            print(tempcomparison)
            raise PuppetConfigRepoError(
                'Unable to migrate between %s and %s environments'
                % (from_env, to_env)
            )

        # Work out the rsync command paths - depends on whether the
        # modules are in both (i.e. take care of empty directory)

        # Create the lists of modules that require different
        left_and_right = [
            module for module in tempcomparison.comparisons
            if tempcomparison.comparisons[module]['left']
            and
            tempcomparison.comparisons[module]['right']
        ]

        left_only = [
            module for module in tempcomparison.comparisons
            if tempcomparison.comparisons[module]['left']
            and
            not tempcomparison.comparisons[module]['right']
        ]

        right_only = [
            module for module in tempcomparison.comparisons
            if not tempcomparison.comparisons[module]['left']
            and
            tempcomparison.comparisons[module]['right']
        ]

        # For each module in the left and right,
        # that is file based, run rsync
        for name in left_and_right:
            module = self.environments[from_env].modules[name]
            if not module.is_submodule:
                try:
                    # Rsync directories
                    rsync = Popen(
                        [
                            'rsync',
                            '-a',
                            '-v',
                            '--delete',
                            '%s/' % module.module_root,
                            self.environments[to_env].\
                            modules[name].module_root
                        ],
                        stdout=PIPE
                    )
                    stdout = rsync.communicate()[0]
                    if rsync.returncode != 0:
                        raise PuppetConfigRepoError(
                            'rsync failed for module %s\n%s'
                            % (name, stdout)
                        )

                except CalledProcessError:
                    if rsync.returncode != 0:
                        raise PuppetConfigRepoError(
                            'rsync failed for module %s\n%s'
                            % (name, stdout)
                        )

        # For each module only in the left
        # that is file based, run rsync
        for name in left_only:
            module = self.environments[from_env].modules[name]
            if not module.is_submodule:
                try:
                    # Rsync directories
                    rsync = Popen(
                        [
                            'rsync',
                            '-a',
                            '-v',
                            '%s' % module.module_root,
                            '%s/modules' % self.environments[to_env].root_dir
                        ],
                        stdout=PIPE
                    )
                    stdout = rsync.communicate()[0]
                    if rsync.returncode != 0:
                        raise PuppetConfigRepoError(
                            'rsync failed for module %s\n%s'
                            % (name, stdout)
                        )

                except CalledProcessError:
                    if rsync.returncode != 0:
                        raise PuppetConfigRepoError(
                            'rsync failed for module %s\n%s'
                            % (name, stdout)
                        )

        # For each module only in the right
        # that is file based, delete it from the right
        for name in right_only:
            module = self.environments[to_env].modules[name]
            if not module.is_submodule:
                try:
                    # Rsync directories
                    rm = Popen(
                        [
                            'rm',
                            '-r',
                            '%s' % module.module_root,
                        ],
                        stdout=PIPE
                    )
                    stdout = rm.communicate()[0]
                    if rm.returncode != 0:
                        raise PuppetConfigRepoError(
                            'rm failed for module %s\n%s'
                            % (name, stdout)
                        )

                except CalledProcessError:
                    if rm.returncode != 0:
                        raise PuppetConfigRepoError(
                            'rm failed for module %s\n%s'
                            % (name, stdout)
                        )

        # Migrate hiera data
        try:
            # Rsync directories
            rsync = Popen(
                [
                    'rsync',
                    '-a',
                    '-v',
                    '--delete',
                    '%s/' % from_hiera,
                    to_hiera
                ],
                stdout=PIPE
            )
            stdout = rsync.communicate()[0]
            if rsync.returncode != 0:
                raise PuppetConfigRepoError(
                    'rsync failed for hieradata\n%s'
                    % stdout
                )

        except CalledProcessError:
            if rsync.returncode != 0:
                raise PuppetConfigRepoError(
                    'rsync failed for hieradata\n%s'
                    % stdout
                )

        # If we are in a repository, commit the changes.
        if self.gitrepo:
            self.gitrepo.add_all()
            self.gitrepo.commit(
                'Migrated changes from %s to %s.'
                % (from_env, to_env)
            )
            self.gitrepo.push()

        # print(tempcomparison)
        # print(self.puppetrepo.env_names())

    def find_environments(self):
        """
        Work out the environments in the current repo
        and return them as PuppetEnvironment objects
        """
        # list the environments directory
        env_base_dir = self.repo_root + '/environments'
        if not os.path.isdir(env_base_dir):
            raise PuppetConfigRepoError(env_base_dir + ' is not a directory.')

        # Create a list of the _directories_ in the environments path
        env_dirs = [
            f for f in os.listdir(env_base_dir)
            if os.path.isdir(env_base_dir + '/' + f)
        ]

        environments = dict()
        for env in env_dirs:
            environments[env] = PuppetEnvironment(env_base_dir + '/' + env)

        return environments

    def __str__(self):
        """
        String representation of a PuppetConfigRepo
        """
        representation = ""
        for env in self.environments.values():
            representation += str(env) + "\n"

        return representation

class PuppetEnvironment(object):
    """
    Models a puppet environment, including git submodules
    and puppet modules.
    """

    def __init__(self, root_dir):
        """
        Constructs information about an environment given a full path to
        the root of the directory tree.
        NOTE: root_dir must be an absolute path
        NOTE: git_submodules should be a dict with
        key = directory, value = commit id
        """
        if not os.path.isdir(root_dir):
            raise PuppetEnvironmentError('Path is not a directory')

        self.my_submodules = dict()
        self.root_dir = root_dir
        self.envname = os.path.basename(self.root_dir)
        self.modules = self.get_puppet_modules()

    def get_puppet_modules(self):
        """
        Return a list of the modules in this environment
        """
        # Check that we have a modules directory
        if not os.path.isdir(self.root_dir + '/modules'):
            raise PuppetEnvironmentError(
                'No modules directory in this environment ('\
                + self.envname + ')'
            )

        # Get a list of the modules installed
        # This checks to see if they are directories before adding
        # them to the module list.
        module_list = [
            f for f in os.listdir(self.root_dir + '/modules')
            if os.path.isdir(self.root_dir + '/modules/' + f)
        ]

        module_dict = dict()
        for module in module_list:
            # Create a new PuppetModule instance for each module
            module_dict[module] = PuppetModule(
                self.root_dir + '/modules/' + module
            )

        return module_dict

    def __str__(self):
        """
        String Representation of a PuppetEnvironment
        """
        representation = 'Env Name: ' + self.envname + "\n"
        representation += 'Root Directory: ' + self.root_dir + "\n"
        representation += "Modules:\n"

        for module in self.modules.values():
            representation += str(module)

        return representation

class PuppetModuleComparison(object):
    """
    Compares 2 module objects
    """

    def __init__(self, leftmodule, rightmodule):
        """
        Run a comparison of 2 PuppetModule Objects
        """
        self.leftmodule = leftmodule
        self.rightmodule = rightmodule
        self.comparisons = {
            'exists_in_both': True,
            'exists_in_left': True,
            'exists_in_right': True,
            'both_same_type': True,
            'both_submodules': True,
            'both_plain_dirs': True,
            'commits_match': True,
            'files_match': True
        }
        self.are_equal = True

        # Basic check to see that the modules passed actually exist
        if self.leftmodule == None:
            # Only in right env
            self.comparisons['exists_in_both'] = False
            self.comparisons['exists_in_left'] = False
            self.comparisons['both_same_type'] = False
            self.comparisons['both_submodules'] = False
            self.comparisons['both_plain_dirs'] = False
            self.comparisons['commits_match'] = False
            self.comparisons['files_match'] = False
            self.are_equal = False
        elif self.rightmodule == None:
            # Only in left env
            self.comparisons['exists_in_both'] = False
            self.comparisons['exists_in_right'] = False
            self.comparisons['both_same_type'] = False
            self.comparisons['both_submodules'] = False
            self.comparisons['both_plain_dirs'] = False
            self.comparisons['commits_match'] = False
            self.comparisons['files_match'] = False
            self.are_equal = False
        else:
            if self.leftmodule.is_submodule != self.rightmodule.is_submodule:
                # Different types of module
                # i.e. one is a submodule, and one is a file based module
                self.comparisons['both_same_type'] = False
                self.comparisons['both_submodules'] = False
                self.comparisons['both_plain_dirs'] = False
                self.are_equal = False
            elif self.leftmodule.is_submodule:
                if self.leftmodule.commit != self.rightmodule.commit:
                    # Both submodules, but commits don't match
                    self.comparisons['commits_match'] = False
                    self.comparisons['both_submodules'] = True
                    self.comparisons['both_plain_dirs'] = False
                    self.are_equal = False
            elif not self.leftmodule.is_submodule:
                # File based modules, check file contents for equality.
                try:
                    # Compare the two directories
                    self.comparisons['commits_match'] = False
                    self.comparisons['both_submodules'] = False
                    self.comparisons['both_plain_dirs'] = True
                    commit = Popen(
                        [
                            'diff',
                            '--brief',
                            '-r',
                            self.leftmodule.module_root,
                            self.rightmodule.module_root
                        ],
                        stdout=PIPE
                    )
                    commit.communicate()

                    if commit.returncode != 0:
                        self.comparisons['files_match'] = False
                        self.are_equal = False

                except CalledProcessError:
                    sys.stderr.write(
                        "Unable to compare module directories\n"
                    )
                    sys.exit(1)

    def get_comparator(self, comparator):
        """
        Returns the value from the comparison dictionary
        """
        return self.comparisons[comparator]

    def __str__(self):
        """
        String representation of a PuppetModuleComparison
        """
        representation = '\tModules are equal: ' + str(self.are_equal) + "\n"
        for name, value in self.comparisons.items():
            representation += '\t' + name + ' : ' + str(value) + "\n"
        return representation



class PuppetEnvComparison(object):
    """
    Represents a comparison between 2 environments
    """

    def __init__(self, leftenv, rightenv):
        """
        Compare 2 Puppet Environments
        """
        self.leftenv = leftenv
        self.rightenv = rightenv
        self.comparisons = dict()
        self.do_comparison()
        self.migratable = None
        self.migration_failure_reasons = dict()
        self.is_migratable()

    def do_comparison(self):
        """
        Do the comparison between the two environments
        """
        # Loop through the left environment, get the module names
        for module in self.leftenv.modules:
            self.comparisons[module] = {
                'left': True,
                'right': False,
                'comparison': ''
            }

        # Do the same for the right
        for module in self.rightenv.modules:
            if module in self.comparisons:
                self.comparisons[module]['right'] = True
            else:
                self.comparisons[module] = {
                    'left': False,
                    'right': True,
                    'comparison': ''
                }

        # Create the comparison objects
        for module in self.comparisons:
            leftenv = None
            rightenv = None
            if self.comparisons[module]['left']:
                leftenv = self.leftenv.modules[module]
            if self.comparisons[module]['right']:
                rightenv = self.rightenv.modules[module]
            self.comparisons[module]['comparison'] =\
                PuppetModuleComparison(leftenv, rightenv)

    def is_migratable(self):
        """
        Returns True if a migration would work between the two
        environments
        """
        value = True
        if self.migratable != None:
            # Just return the value
            value = self.migratable
        else:
            # Calculate if we are migratable
            for module in self.comparisons:
                comparison = self.comparisons[module]['comparison']
                if comparison.are_equal:
                    continue

                # Only exists in left, and it is a submodule
                # Requires manual git intervention
                elif (\
                    comparison.get_comparator('exists_in_left')\
                    and not comparison.get_comparator('exists_in_right')\
                ) and self.leftenv.modules[module].is_submodule:
                    value = False
                    self.migration_failure_reasons[module] =\
                        'Only in left, and is a submodule'

                # Only exists in right, and it is a submodule
                # Requires manual git intervention
                elif (\
                    comparison.get_comparator('exists_in_right')\
                    and not comparison.get_comparator('exists_in_left')\
                )\
                and self.rightenv.modules[module].is_submodule:
                    value = False
                    self.migration_failure_reasons[module] =\
                        'Only in right, and is a submodule'

                # Exists in both, but are of different types
                elif comparison.get_comparator('exists_in_both')\
                and\
                not comparison.get_comparator('both_same_type'):
                    value = False
                    self.migration_failure_reasons[module] =\
                        'In both but one is a submodule and one isn\'t'

                # Both are submodules, with different commits
                elif comparison.get_comparator('both_submodules')\
                and\
                not comparison.get_comparator('commits_match'):
                    value = False
                    self.migration_failure_reasons[module] =\
                        'Both are submodules, but commits don\'t match'

        return value

    def __str__(self):
        """
        String representation of a PuppetEnvComparison
        """
        representation = "Left Environment: " + self.leftenv.envname + "\n"
        representation += "Right Environment: " + self.rightenv.envname + "\n"
        representation +=\
            "Can migrate from left to right? "\
            + str(self.is_migratable()) + "\n"
        if not self.is_migratable():
            representation += "Reasons for being unable to migrate:\n"
            for name, value in self.migration_failure_reasons.items():
                representation += "\t" + name + " : " + value + "\n"

        for module in self.comparisons:
            representation += 'Module name: ' + module + "\n"
            representation += str(self.comparisons[module]['comparison'])
        return representation
