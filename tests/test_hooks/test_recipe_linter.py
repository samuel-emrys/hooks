# coding=utf-8

import os
import textwrap
import unittest

import six
from packaging import version
from parameterized import parameterized

from conans import __version__ as conan_version
from conans import tools
from conans.client.command import ERROR_GENERAL, SUCCESS
from conans.tools import environment_append
from tests.utils.test_cases.conan_client import ConanClientTestCase


class RecipeLinterTests(ConanClientTestCase):
    conanfile = textwrap.dedent(r"""
        from conan import ConanFile, tools
        
        class TestConan(ConanFile):
            name = "name"
            version = "version"
            
            def build(self):
                print("Hello world")    
                for k, v in {}.iteritems():
                    pass
                tools.msvc_build_command(self.settings, "path")
        """)

    def _get_environ(self, **kwargs):
        kwargs = super(RecipeLinterTests, self)._get_environ(**kwargs)
        kwargs.update({'CONAN_HOOKS': os.path.join(os.path.dirname(
            __file__), '..', '..', 'hooks', 'recipe_linter')})
        return kwargs

    @parameterized.expand([(False, ), (True, )])
    def test_basic(self, pylint_werr):
        tools.save('conanfile.py', content=self.conanfile)
        pylint_werr_value = "1" if pylint_werr else None
        with environment_append({"CONAN_PYLINT_WERR": pylint_werr_value}):
            return_code = ERROR_GENERAL if pylint_werr else SUCCESS
            output = self.conan(['export', '.', 'name/version@'], expected_return_code=return_code)

            if pylint_werr:
                self.assertIn("pre_export(): Package recipe has linter errors."
                              " Please fix them.", output)

            if six.PY2:
                self.assertIn("pre_export(): conanfile.py:9:8:"
                              " E1601: print statement used (print-statement)", output)
                self.assertIn("pre_export(): conanfile.py:10:20:"
                              " W1620: Calling a dict.iter*() method (dict-iter-method)", output)
            else:
                self.assertIn("pre_export(): conanfile.py:10:20:"
                              " E1101: Instance of 'dict' has no 'iteritems' member (no-member)",
                              output)

            self.assertIn("pre_export(): conanfile.py:10:12:"
                          " W0612: Unused variable 'k' (unused-variable)", output)
            self.assertIn("pre_export(): conanfile.py:10:15:"
                          " W0612: Unused variable 'v' (unused-variable)", output)

    def test_path_with_spaces(self):
        conanfile = textwrap.dedent(r"""
            from conan import ConanFile

            class Recipe(ConanFile):
                def build(self):
                    pass
        """)
        tools.save(os.path.join("path spaces", "conanfile.py"), content=conanfile)
        output = self.conan(['export', 'path spaces/conanfile.py', 'name/version@'])
        recipe_path = os.path.join(os.getcwd(), "path spaces", "conanfile.py")
        self.assertIn("pre_export(): Lint recipe '{}'".format(recipe_path), output)
        self.assertIn("pre_export(): Linter detected '0' errors", output)

    def test_custom_rcfile(self):
        tools.save('conanfile.py', content=self.conanfile)
        tools.save('pylintrc', content="[FORMAT]\nindent-string='  '")

        with environment_append({"CONAN_PYLINTRC": os.path.join(os.getcwd(), "pylintrc")}):
            output = self.conan(['export', '.', 'name/version@'])
        self.assertIn("pre_export(): conanfile.py:5:0: "
                      "W0311: Bad indentation. Found 4 spaces, expected 2 (bad-indentation)", output)

    def test_custom_plugin(self):
        conanfile = textwrap.dedent(r"""
            from conan import ConanFile

            class Recipe(ConanFile):
                def build(self):
                    self.output.info(self.conan_data)
        """)
        tools.save('conanfile.py', content=conanfile)
        with environment_append({"CONAN_PYLINT_WERR": "1"}):
            # With the default 'python_plugin' it doesn't raise
            with environment_append({"CONAN_PYLINT_RECIPE_PLUGINS": None}):
                output = self.conan(['export', '.', 'consumer/version@'])
                self.assertIn("pre_export(): Lint recipe", output)  # Hook run without errors
                self.assertIn("pre_export(): Linter detected '0' errors", output)

            # With a custom one, it should fail
            tools.save("plugin_empty.py", content="def register(_):\n\tpass")
            with environment_append({"CONAN_PYLINT_RECIPE_PLUGINS": "plugin_empty"}):
                output = self.conan(['export', '.', 'consumer/other@'], expected_return_code=ERROR_GENERAL)
                self.assertIn("pre_export(): Package recipe has linter errors."
                              " Please fix them.", output)

    def test_dynamic_fields(self):
        conanfile = textwrap.dedent("""
            from conan import ConanFile
            
            class TestConan(ConanFile):
                name = "consumer"
                version = "version"
                
                def build(self):
                    self.output.info(self.source_folder)
                    self.output.info(self.package_folder)
                    self.output.info(self.build_folder)
                    self.output.info(self.install_folder)
                    
                def package(self):
                    self.copy("*")
                    
                def package_id(self):
                    self.info.header_only()
                    
                def build_id(self):
                    self.output.info(str(self.info_build))
                    
                def build_requirements(self):
                    self.build_requires("name/version")
                    
                def requirements(self):
                    self.requires("name/version")
                    
                def deploy(self):
                    self.copy_deps("*.dll")
            """)
        tools.save('consumer.py', content=conanfile)
        with environment_append({"CONAN_PYLINT_WERR": "1"}):
            output = self.conan(['export', 'consumer.py', 'consumer/version@'])
            self.assertIn("pre_export(): Lint recipe", output)  # Hook run without errors
            self.assertIn("pre_export(): Linter detected '0' errors", output)
            self.assertNotIn("(no-member)", output)

    def test_catch_them_all(self):
        conanfile = textwrap.dedent("""
            from conan import ConanFile
            class BaseConan(ConanFile):

                def source(self):
                    try:
                        raise Exception("Pikaaaaa!!")
                    except:
                        pass
                    try:
                        raise Exception("Pikaaaaa!!")
                    except Exception:
                        pass
            """)

        tools.save('conanfile.py', content=conanfile)
        with environment_append({"CONAN_PYLINT_WERR": "1"}):
            output = self.conan(['export', '.', 'consumer/version@'])
            self.assertIn("pre_export(): Lint recipe", output)  # Hook run without errors
            self.assertIn("pre_export(): Linter detected '0' errors", output)
            self.assertNotIn("no-member", output)

    def test_conan_data(self):
        conanfile = textwrap.dedent("""
            from conan import ConanFile
        
            class ExampleConan(ConanFile):
    
                def build(self):
                    _ = self.conan_data["sources"][float(self.version)]
            """)
        tools.save('conanfile.py', content=conanfile)
        with environment_append({"CONAN_PYLINT_WERR": "1"}):
            output = self.conan(['export', '.', 'consumer/version@'])
            self.assertIn("pre_export(): Lint recipe", output)  # Hook run without errors
            self.assertIn("pre_export(): Linter detected '0' errors", output)
            self.assertNotIn("no-member", output)

    @unittest.skipUnless(version.parse(conan_version) >= version.parse("1.21.0"), "Need python_version")
    def test_python_requires(self):
        """ python_requires were not added to the 'pylint_plugin' until 1.21 """
        pytreq_conanfile = textwrap.dedent("""
            from conan import ConanFile
            class TestConan(ConanFile):
                pass
            """)
        tools.save('pyrequire.py', pytreq_conanfile)
        self.conan(['export', 'pyrequire.py', 'package/version@user/channel'])
        conanfile = textwrap.dedent("""
            from conan import ConanFile

            class TestConan(ConanFile):
                name = "consumer"
                version = "version"
                python_requires = "package/version@user/channel"
            """)
        tools.save('require.py', conanfile)
        self.conan(['export', 'require.py', 'consumer/version@'])

        tools.save('consumer.py', content=conanfile)
        with environment_append({"CONAN_PYLINT_WERR": "1"}):
            output = self.conan(['export', 'consumer.py', 'consumer/version@'])
            self.assertIn("pre_export(): Lint recipe", output)  # Hook run without errors
            self.assertIn("pre_export(): Linter detected '0' errors", output)
            self.assertNotIn("(no-name-in-module)", output)
