"""
Git Repo manipulation library
"""
import re
import os
import sys
from subprocess import *

class GitRepoError(Exception):
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

class GitRepo(object):
    """
    Representation of a git repository
    """
    def __init__(self, starting_dir):
        """
        Gather information on the current git repo
        NOTE: starting_dir is a full path
        """
        if not os.path.isdir(starting_dir):
            raise GitRepoError('Path ' + starting_dir + ' is not a directory')

        self.root_dir = self.find_repo_root(starting_dir)
        self.submodules = self.find_submodules()

    @classmethod
    def find_repo_root(cls, starting_dir):
        """
        Find the root directory of the current repository
        based on the current working directory
        NOTE: This will change to working directory
        """
        # Change into the base directory
        os.chdir(starting_dir)
        # Run the git status command
        git_status = Popen(['git', 'status'], stdout=PIPE, stderr=PIPE)
        (stdout, stderr) = git_status.communicate()

        # Parse each line of the file, and add the module_path
        # to the corresponding environment
        fatal_error = re.compile(r'^fatal: Not a git repository')
        for line in stderr.decode('utf-8').split('\n'):
            matches = fatal_error.search(line)
            if matches:
                raise GitRepoError('Not inside a git repository.')

        # Find a .gitmodules file in the current file path
        git_root_dir = './'
        while not os.path.isdir(git_root_dir + '.git'):
            git_root_dir = "../" + git_root_dir

        # Change into the root directory to allow the rest of the
        # program to have a sane starting point, and return the
        # full path of the root dir
        return os.path.abspath(git_root_dir)

    @classmethod
    def find_submodules(cls):
        """
        Gets the submodules configured for this repository
        """
        module_dict = dict()

        modules_re = re.compile(
            r'\s+(?P<revision>.*?)'\
            r'\s+(?P<path>.*?)'\
            r'\s+\((?P<tag>.*?)\)$'
        )

        try:
            # Run the git status command
            submodule_command = Popen(['git', 'submodule'], stdout=PIPE)
            stdout = submodule_command.communicate()[0]

            # Parse each line of the file, and add the module_path
            # to the corresponding environment
            for line in stdout.decode('utf-8').split('\n'):
                matches = modules_re.search(line)
                if matches:
                    path = matches.group('path')
                    module_dict[path] = {
                        'revision':matches.group('revision'),
                        'tag':matches.group('tag')
                    }
            return module_dict

        except CalledProcessError:
            sys.stderr.write("Unable to get current branch name\n")
            sys.exit(1)

    def current_branch(self):
        """
        Get the current branch
        """
        branchre = re.compile(r'^On branch (?P<branchname>.*)$')
        branchname = ''

        try:
            # Get the current branch
            status = Popen(['git', 'status'], stdout=PIPE)

            # Parse each line of the file, and add the module_path
            # to the corresponding environment
            stdout = status.communicate()[0]
            for line in stdout.decode('utf-8').split('\n'):
                matches = branchre.search(line)
                if matches:
                    branchname = matches.group('branchname')

            if status.returncode != 0:
                raise GitRepoError(
                    'Could not determine the current branch\n'
                )

            return branchname

        except CalledProcessError:
            if status.returncode != 0:
                raise GitRepoError(
                    'Could not determine the current branch\n'
                )

    def commit(self, commit_message):
        """
        Commit the current changes with current changes
        """
        nothingtocommitre = re.compile(
            r'.*nothing to commit, working directory clean.*'
        )
        try:
            # Commit the current changes.
            commit = Popen(
                [
                    'git',
                    'commit',
                    '-m',
                    '%s' % commit_message,
                    '-a',
                ],
                stdout=PIPE
            )
            stdout = commit.communicate()[0]

            if commit.returncode != 0:
                match = nothingtocommitre.search(stdout.decode('utf-8'))
                if not match:
                    raise GitRepoError(
                        'Could not commit changes\n%s'
                        % stdout
                    )

        except CalledProcessError:
            if commit.returncode != 0:
                raise GitRepoError(
                    'Could not commit changes\n%s'
                    % stdout
                )

    def add_all(self):
        """
        Add all the unknown files, ready for commit
        """
        try:
            # Add all the files, staring from the root
            git_add = Popen(
                [
                    'git',
                    'add',
                    self.root_dir,
                ],
                stdout=PIPE
            )
            stdout = git_add.communicate()[0]
            if git_add.returncode != 0:
                raise GitRepoError(
                    'Could not commit changes\n%s'
                    % stdout.decode('utf-8')
                )

        except CalledProcessError:
            if git_add.returncode != 0:
                raise GitRepoError(
                    'Could not commit changes\n%s'
                    % stdout
                )

    def push(self, remote='origin', force=False):
        """
        Push the changes to the repository.
        """
        if force:
            command = [
                'git',
                'push',
                '--force',
                remote,
                self.current_branch()
            ]
        else:
            command = [
                'git',
                'push',
                remote,
                self.current_branch()
            ]

        try:
            # Commit the current changes.
            commit = Popen(
                command,
                stdout=PIPE,
                stderr=PIPE
            )
            (stdout, stderr) = commit.communicate()
            if commit.returncode != 0:
                raise GitRepoError(
                    'Could not commit changes\n%s'
                    % stdout.decode('utf-8')
                )

        except CalledProcessError:
            if commit.returncode != 0:
                raise GitRepoError(
                    'Could not commit changes\n%s'
                    % stdout.decode('utf-8')
                )
