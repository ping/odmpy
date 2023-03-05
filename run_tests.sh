set -e

coverage erase

# test1.odm - book with ascii meta
# test2.odm - book with non-ascii meta
# test3.odm - Issue using mutagen, ref #17
# test4.odm - HTML entities decoding, ref #19

for test_index in '1' '2' '3' '4'
do
  export TEST_ODM="test${test_index}.odm"
  echo "======================= Testing with ${TEST_ODM} ======================="

  # Tests for `odmpy info` command
  coverage run --append -m unittest -v tests.OdmpyTests.test_info
  coverage run --append -m unittest -v tests.OdmpyTests.test_info_json

  # Tests for `odmpy dl` command
  coverage run --append -m unittest -v tests.OdmpyDlTests

  unset TEST_ODM
done
echo '======================================================================'

# Misc Tests
# test fix for #24 cover download fail
TEST_ODM="test_ref24.odm" coverage run --append -m unittest -v tests.OdmpyTests.test_cover_fail_ref24
# test for #26 opf generation
TEST_ODM="test1.odm" coverage run --append -m unittest -v tests.OdmpyTests.test_opf

# Tests for `odmpy libby` command
coverage run --append -m unittest -v tests.OdmpyLibbyTests

# Tests for odmpy.libby
coverage run --append -m unittest -v tests.LibbyClientTests

# Test for odmpy.overdrive
coverage run --append -m unittest -v tests.OverDriveClientTests

# Tests for odmpy.utils
coverage run --append -m unittest -v tests.UtilsTests

# Tests for odmpy.processing.shared
coverage run --append -m unittest -v tests.ProcessingSharedTests
