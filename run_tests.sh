set -e

# test1.odm - book with ascii meta
# test2.odm - book with non-ascii meta
# test3.odm - Issue using mutagen, ref #17
# test4.odm - HTML entities decoding, ref #19

for test_index in '1' '2' '3' '4'
do
  export TEST_ODM="test${test_index}.odm"
  echo "======================= Testing with ${TEST_ODM} ======================="

  # Tests for `odmpy info` command
  python -m unittest -v tests.OdmpyTests.test_info
  python -m unittest -v tests.OdmpyTests.test_info_json

  # Tests for `odmpy dl` command
  python -m unittest -v tests.OdmpyDlTests

  unset TEST_ODM
done
echo '======================================================================'

# Misc Tests
# test fix for #24 cover download fail
TEST_ODM="test_ref24.odm" python -m unittest -v tests.OdmpyTests.test_cover_fail_ref24
# test for #26 opf generation
TEST_ODM="test1.odm" python -m unittest -v tests.OdmpyTests.test_opf

# Tests for `odmpy libby` command
python -m unittest -v tests.OdmpyLibbyTests

# Tests for odmpy.libby
python -m unittest -v tests.LibbyClientTests

# Tests for odmpy.utils
python -m unittest -v tests.UtilsTests

# Tests for odmpy.processing.shared
python -m unittest -v tests.ProcessingSharedTests
