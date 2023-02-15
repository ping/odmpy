set -e

# test1.odm - book with ascii meta
# test2.odm - book with non-ascii meta
# test3.odm - Issue using mutagen, ref #17
# test4.odm - HTML entities decoding, ref #19

export TEST_DATA_DIR='tests/data'
export TEST_DOWNLOAD_DIR="$TEST_DATA_DIR/downloads/"
mkdir -p "$TEST_DOWNLOAD_DIR"

for test_index in '1' '2' '3' '4'
do
  export TEST_ODM="test${test_index}.odm"

  echo "-=-=-=-=-=-=-=-=-=- RUNNING TESTS FOR $TEST_ODM ... -=-=-=-=-=-=-=-=-=-"

  # test info function
  mkdir -p "$TEST_DOWNLOAD_DIR"
  python -m odmpy info "$TEST_DATA_DIR/$TEST_ODM" > "${TEST_DOWNLOAD_DIR}test.odm.info.txt"
  python -m unittest -v tests.OdmpyTests.test_info

  # test info - json function
  mkdir -p "$TEST_DOWNLOAD_DIR"
  python -m odmpy info -f json "$TEST_DATA_DIR/$TEST_ODM" > "${TEST_DOWNLOAD_DIR}test.odm.info.json"
  python -m unittest -v tests.OdmpyTests.test_info_json

  python -m unittest -v tests.OdmpyDlTests

done

echo "-=-=-=-=-=-=-=-=-=- RUNNING MISC TESTS ... -=-=-=-=-=-=-=-=-=-"
# test fix for #24 cover download fail
TEST_ODM="test_ref24.odm" python -m unittest -v tests.OdmpyTests.test_cover_fail_ref24
# test for #26 opf generation
TEST_ODM="test1.odm" python -m unittest -v tests.OdmpyTests.test_opf

echo "-=-=-=-=-=-=-=-=-=- RUNNING TESTS FOR LIBBY CLIENT ... -=-=-=-=-=-=-=-=-=-"
python -m unittest -v tests.LibbyClientTests

echo "-=-=-=-=-=-=-=-=-=- RUNNING TESTS FOR UTILS ... -=-=-=-=-=-=-=-=-=-"
python -m unittest -v tests.UtilsTests

echo "-=-=-=-=-=-=-=-=-=- RUNNING TESTS FOR ODMPY LIBBY COMMANDS ... -=-=-=-=-=-=-=-=-=-"
python -m unittest -v tests.OdmpyLibbyTests
