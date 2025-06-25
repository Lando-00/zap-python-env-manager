import unittest
import subprocess
import os
import shutil
import sys
from pathlib import Path
import tempfile

# Path to the script to be tested
SCRIPT_PATH = Path(__file__).resolve().parent / "zap.py"

def get_an_available_python_version():
    """
    Attempts to get an available Python version tag recognized by zap.py.
    This is used by the tests to create virtual environments.
    """
    try:
        # Use the Python interpreter that's running this test script
        python_exe_for_tests = sys.executable
        cmd = [python_exe_for_tests, str(SCRIPT_PATH), "list"]
        print(f"Attempting to find a Python version using: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)
        
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            # Look for lines like "  3.11        -> C:\Python311\python.exe"
            # under ">> Available Python interpreters:"
            in_py_section = False
            for line in lines:
                if "Available Python interpreters" in line:
                    in_py_section = True
                    continue
                if "Virtual environments in" in line: # Reached next section
                    in_py_section = False
                    break
                if in_py_section and "->" in line:
                    version_tag = line.strip().split("->")[0].strip()
                    if version_tag and "." in version_tag: # Basic sanity check for a version string
                        print(f"Auto-detected test Python version: {version_tag}")
                        return version_tag
            print("Could not parse a Python version from 'zap list' output.")
        else:
            print(f"'zap list' command failed with rc={result.returncode}:")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")

    except subprocess.TimeoutExpired:
        print(f"'zap list' command timed out.")
    except Exception as e:
        print(f"Could not auto-detect Python version for testing due to an error: {e}")
    
    # Fallback if auto-detection fails
    fallback_version = "3.11-arm64" # Match your system's Python version
    print(f"Falling back to hardcoded Python version '{fallback_version}' for testing. "
          f"Ensure this version is usable by 'zap.py create'.")
    return fallback_version

TEST_PYTHON_VERSION = get_an_available_python_version()
TEST_ENV_NAME = "test_env_xyz123" # Unique name for test environment

class TestZap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_env_root = os.environ.get("ENV_ROOT")
        cls.temp_dir_manager = tempfile.TemporaryDirectory()
        cls.test_env_root = Path(cls.temp_dir_manager.name) / "test_venvs_root"
        os.environ["ENV_ROOT"] = str(cls.test_env_root)
        
        # Ensure the test_env_root itself exists, as zap.py expects ENV_ROOT to be creatable
        cls.test_env_root.mkdir(parents=True, exist_ok=True)

        print(f"\nSetting temporary ENV_ROOT for tests: {cls.test_env_root}")
        print(f"Using Python version for tests: {TEST_PYTHON_VERSION}")

    @classmethod
    def tearDownClass(cls):
        if cls.original_env_root is None:
            if "ENV_ROOT" in os.environ: # Check if it was set by us
                 del os.environ["ENV_ROOT"]
        else:
            os.environ["ENV_ROOT"] = cls.original_env_root
        
        cls.temp_dir_manager.cleanup()
        print(f"\n--- Test Cleanup Complete ---")
        print(f"Temporary test ENV_ROOT {cls.test_env_root} has been deleted.")

    def _run_zap(self, command_args, expect_success=True, input_data=None):
        # Use the Python interpreter that's running this test script to run zap.py
        python_exe_for_tests = sys.executable
        cmd = [python_exe_for_tests, str(SCRIPT_PATH)] + command_args
        
        command_str = ' '.join(cmd)
        if input_data:
            command_str += f" (input: '{input_data.strip()}')"
        print(f"\nExecuting: {command_str}")

        try:
            process = subprocess.run(cmd, capture_output=True, text=True, input=input_data, check=False, timeout=30)
            output = process.stdout.strip()
            # zap.py often prints errors to stdout via sys.exit(message)
            # but actual stderr might also contain info if subprocess.run within zap.py fails differently
            if process.stderr.strip():
                output += "\nStderr:\n" + process.stderr.strip()

            print(f"Return Code: {process.returncode}")
            if output:
                print(f"Output:\n{output}")

            if expect_success:
                self.assertEqual(process.returncode, 0, f"zap command '{' '.join(command_args)}' failed unexpectedly.\nOutput:\n{output}")
            return process.returncode, output
        except subprocess.TimeoutExpired:
            self.fail(f"zap command '{' '.join(command_args)}' timed out after 30 seconds.")


    def test_01_list_initial(self):
        print("\n--- Test Case: zap list (initial) ---")
        rc, output = self._run_zap(["list"])
        self.assertIn("Available Python interpreters", output)
        self.assertTrue(str(self.test_env_root) in output, f"Test ENV_ROOT path missing in output. Got: {output}")
        # No specific env should be listed under TEST_PYTHON_VERSION yet
        self.assertNotIn(f"* {TEST_ENV_NAME}", output)

    def test_02_create_env_invalid_python_version(self):
        print("\n--- Test Case: zap create (invalid python version) ---")
        invalid_python_version = "0.0-nonexistentversion"
        env_name_invalid_py = "env_with_invalid_py"
        rc, output = self._run_zap(["create", invalid_python_version, env_name_invalid_py], expect_success=False)
        self.assertNotEqual(rc, 0)
        self.assertIn(f"Python {invalid_python_version} not found", output)
        env_dir = self.test_env_root / invalid_python_version / env_name_invalid_py
        self.assertFalse(env_dir.exists(), f"Environment directory {env_dir} should not have been created with invalid python.")

    def test_03_create_env(self):
        print(f"\n--- Test Case: zap create {TEST_PYTHON_VERSION} {TEST_ENV_NAME} ---")
        rc, output = self._run_zap(["create", TEST_PYTHON_VERSION, TEST_ENV_NAME])
        self.assertIn("Creating venv at", output) # Message before creation
        self.assertIn("Success!", output)
        env_dir = self.test_env_root / TEST_PYTHON_VERSION / TEST_ENV_NAME
        self.assertTrue(env_dir.exists(), f"Environment directory {env_dir} was not created.")
        self.assertTrue((env_dir / "pyvenv.cfg").exists(), f"pyvenv.cfg not found in new env at {env_dir}.")
        print(f"Verified: Environment {TEST_ENV_NAME} created at {env_dir}")

    def test_04_create_env_already_exists(self):
        print("\n--- Test Case: zap create (already exists) ---")
        # Assumes test_03_create_env ran and created the env
        rc, output = self._run_zap(["create", TEST_PYTHON_VERSION, TEST_ENV_NAME], expect_success=False)
        self.assertNotEqual(rc, 0)
        self.assertIn(f"Environment {TEST_ENV_NAME} already exists.", output)

    def test_05_list_after_create(self):
        print("\n--- Test Case: zap list (after create) ---")
        # Assumes test_03_create_env ran
        rc, output = self._run_zap(["list"])
        self.assertIn(f"Python {TEST_PYTHON_VERSION}", output)
        self.assertIn(f"* {TEST_ENV_NAME}", output)

    def test_06_activate_env_show_command(self):
        print(f"\n--- Test Case: zap activate {TEST_ENV_NAME} (show command) ---")
        # Assumes test_03_create_env ran
        rc, output = self._run_zap(["activate", TEST_ENV_NAME])
        env_dir = self.test_env_root / TEST_PYTHON_VERSION / TEST_ENV_NAME
        expected_cmd_part = ""
        if os.name == "nt":
            # Need to escape backslashes for regex-like matching in assertIn, or use raw strings
            # For simple assertIn, direct string is fine.
            expected_cmd_part = str(env_dir / "Scripts" / "Activate.ps1")
        else:
            expected_cmd_part = str(env_dir / "bin" / "activate")
        self.assertIn(expected_cmd_part, output)

    def test_07_activate_env_non_existent(self):
        print("\n--- Test Case: zap activate (non-existent) ---")
        non_existent_env_name = "env_does_not_exist_for_activate"
        rc, output = self._run_zap(["activate", non_existent_env_name], expect_success=False)
        self.assertNotEqual(rc, 0)
        self.assertIn(f"No environment named '{non_existent_env_name}'", output)

    def test_08_delete_env_cancel(self):
        print("\n--- Test Case: zap delete (cancel) ---")
        temp_env_name_for_cancel = f"{TEST_ENV_NAME}_to_cancel_delete"
        # Create this temporary env first
        self._run_zap(["create", TEST_PYTHON_VERSION, temp_env_name_for_cancel])
        env_dir_cancel = self.test_env_root / TEST_PYTHON_VERSION / temp_env_name_for_cancel
        self.assertTrue(env_dir_cancel.exists(), "Pre-requisite for cancel test: env should exist.")

        rc, output = self._run_zap(["delete", temp_env_name_for_cancel], input_data="n\n", expect_success=True) # cmd itself is success
        self.assertEqual(rc, 0) # Should exit cleanly if user cancels
        self.assertTrue(env_dir_cancel.exists(), f"Environment directory {env_dir_cancel} was deleted despite cancellation.")
        # Clean up this temp env manually as deletion was cancelled
        shutil.rmtree(env_dir_cancel, ignore_errors=True)
        self.assertFalse(env_dir_cancel.exists(), "Cleanup of cancelled env failed.")


    def test_09_delete_env_confirm(self):
        print(f"\n--- Test Case: zap delete {TEST_ENV_NAME} (confirm) ---")
        # Assumes test_03_create_env ran and env exists
        env_dir = self.test_env_root / TEST_PYTHON_VERSION / TEST_ENV_NAME
        self.assertTrue(env_dir.exists(), f"Pre-requisite for delete test: env {TEST_ENV_NAME} should exist.")

        rc, output = self._run_zap(["delete", TEST_ENV_NAME], input_data="y\n")
        self.assertIn("Done.", output)
        self.assertFalse(env_dir.exists(), f"Environment directory {env_dir} was not deleted after confirmation.")

    def test_10_delete_env_non_existent(self):
        print("\n--- Test Case: zap delete (non-existent) ---")
        non_existent_env_name = "env_already_gone_or_never_existed"
        rc, output = self._run_zap(["delete", non_existent_env_name], input_data="y\n", expect_success=False)
        self.assertNotEqual(rc, 0)
        self.assertIn(f"No env named '{non_existent_env_name}'", output)

    def test_11_list_after_all_deletions(self):
        print("\n--- Test Case: zap list (after all deletions) ---")
        # Assumes test_09_delete_env_confirm deleted TEST_ENV_NAME
        # Assumes test_08_delete_env_cancel cleaned up its own temp env
        rc, output = self._run_zap(["list"])
        self.assertNotIn(f"* {TEST_ENV_NAME}", output, "Main test env should not be listed.")
        self.assertNotIn(f"* {TEST_ENV_NAME}_to_cancel_delete", output, "Cancelled delete test env should not be listed.")

def run_tests_and_summarize():
    print("Starting Zap Test Suite...")
    print("======================================================================")
    
    # Ensure SCRIPT_PATH is correct
    if not SCRIPT_PATH.exists():
        print(f"ERROR: zap.py not found at expected path: {SCRIPT_PATH}")
        print("Please ensure test_zap.py is in the same directory as zap.py.")
        return False
        
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(TestZap))

    runner = unittest.TextTestRunner(verbosity=2, failfast=False)
    result = runner.run(suite)

    print("======================================================================")
    print("--- Test Summary ---")
    passed_count = result.testsRun - len(result.failures) - len(result.errors)
    print(f"Total tests run: {result.testsRun}")
    print(f"Tests passed: {passed_count}")
    print(f"Tests failed: {len(result.failures)}")
    print(f"Tests with errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ All tests passed successfully!")
    else:
        print("\n❌ Some tests failed or had errors.")
        # Detailed failures/errors are already printed by TextTestRunner verbosity=2
    
    print("======================================================================")
    return result.wasSuccessful()

if __name__ == "__main__":
    all_passed = run_tests_and_summarize()
    # Exit with status code 0 if all passed, 1 otherwise, useful for CI
    # sys.exit(0 if all_passed else 1)
