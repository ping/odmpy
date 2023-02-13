set -e

# test1.odm - book with ascii meta
# test2.odm - book with non-ascii meta
# test3.odm - Issue using mutagen, ref #17
# test4.odm - HTML entities decoding, ref #19

export TEST_DATA_DIR='tests/data'
export TEST_DOWNLOAD_DIR="$TEST_DATA_DIR/downloads/"

clear_test_data () {
    # clean up
    rm -rf "$TEST_DOWNLOAD_DIR"
    rm -rf "$TEST_DATA_DIR"/*.json
    rm -rf "$TEST_DATA_DIR"/test*.odm.info.txt
    rm -rf "$TEST_DATA_DIR"/output.mp3*
    rm -ff "$TEST_DATA_DIR"/output.m4b*
}

for test_index in '1' '2' '3' '4'
do
  export TEST_ODM="test${test_index}.odm"

  clear_test_data

  echo "-=-=-=-=-=-=-=-=-=- RUNNING TESTS FOR $TEST_ODM ... -=-=-=-=-=-=-=-=-=-"

  # test info function
  rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
  python -m odmpy info "$TEST_DATA_DIR/$TEST_ODM" > "$TEST_DATA_DIR/test.odm.info.txt"
  python -m unittest -v tests.OdmpyTests.test_info

  # test info - json function
  rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
  python -m odmpy info -f json "$TEST_DATA_DIR/$TEST_ODM" > "$TEST_DATA_DIR/test.odm.info.json"
  python -m unittest -v tests.OdmpyTests.test_info_json

  # standard download
  rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
  python -m odmpy dl "$TEST_DATA_DIR/$TEST_ODM" -d "$TEST_DOWNLOAD_DIR" -k --hideprogress > /dev/null
  python -m unittest -v tests.OdmpyTests.test_download_1

  # download + add chapter marks
  rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
  python -m odmpy dl "$TEST_DATA_DIR/$TEST_ODM" -d "$TEST_DOWNLOAD_DIR" -c --hideprogress > /dev/null
  python -m unittest -v tests.OdmpyTests.test_download_4

  # download + merge into mp3
  rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
  python -m odmpy dl "$TEST_DATA_DIR/$TEST_ODM" -d "$TEST_DOWNLOAD_DIR" -m --hideprogress > /dev/null
  python -m unittest -v tests.OdmpyTests.test_download_2
  # download + merge into m4b
  python -m odmpy dl "$TEST_DATA_DIR/$TEST_ODM" -d "$TEST_DOWNLOAD_DIR" -m --mergeformat m4b --hideprogress > /dev/null
  python -m unittest -v tests.OdmpyTests.test_download_3

  # download + merge into mp3 + add chapter marks
  rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
  rm  -f "$TEST_DATA_DIR"/output.mp3*
  python -m odmpy dl "$TEST_DATA_DIR/$TEST_ODM" -d "$TEST_DOWNLOAD_DIR" -c -m --hideprogress > /dev/null
  mv "$TEST_DOWNLOAD_DIR"/*/*Herrick.mp3 "$TEST_DOWNLOAD_DIR/output.mp3"
  ffprobe -v quiet -print_format json -show_format -show_streams -show_chapters \
  "$TEST_DOWNLOAD_DIR/output.mp3" > "$TEST_DATA_DIR/output.mp3.json"
  python -m unittest -v tests.OdmpyTests.test_download_5

  # download + merge into m4b + add chapter marks
  rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
  rm  -f "$TEST_DATA_DIR"/output.m4b*
  python -m odmpy dl "$TEST_DATA_DIR/$TEST_ODM" -d "$TEST_DOWNLOAD_DIR" -c -m --mergeformat m4b --hideprogress > /dev/null
  mv "$TEST_DOWNLOAD_DIR"/*/*Herrick.m4b "$TEST_DOWNLOAD_DIR/output.m4b"
  ffprobe -v quiet -print_format json -show_format -show_streams -show_chapters \
  "$TEST_DOWNLOAD_DIR/output.m4b" > "$TEST_DATA_DIR/output.m4b.json"
  python -m unittest -v tests.OdmpyTests.test_download_6

  # download + merge + don't create book folder
  rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
  python -m odmpy dl "$TEST_DATA_DIR/$TEST_ODM" -d "$TEST_DOWNLOAD_DIR" -m --nobookfolder --hideprogress > /dev/null
  python -m unittest -v tests.OdmpyTests.test_download_7

  # clean up
  clear_test_data

done

# test fix for #24 cover download fail
export TEST_ODM="test_ref24.odm"
echo "-=-=-=-=-=-=-=-=-=- RUNNING TESTS FOR $TEST_ODM ... -=-=-=-=-=-=-=-=-=-"
rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
python -m odmpy dl "$TEST_DATA_DIR/test_ref24.odm" -d "$TEST_DOWNLOAD_DIR" -k --hideprogress > /dev/null
python -m unittest -v tests.OdmpyTests.test_cover_fail_ref24

export TEST_ODM="test1.odm"
echo "-=-=-=-=-=-=-=-=-=- RUNNING TESTS FOR OPF $TEST_ODM ... -=-=-=-=-=-=-=-=-=-"
rm -rf "$TEST_DOWNLOAD_DIR" && mkdir -p "$TEST_DOWNLOAD_DIR"
python -m odmpy dl "$TEST_DATA_DIR/$TEST_ODM" -d "$TEST_DOWNLOAD_DIR" -k --opf --hideprogress > /dev/null
python -m unittest -v tests.OdmpyTests.test_opf

echo "-=-=-=-=-=-=-=-=-=- RUNNING TESTS FOR LIBBY CLIENT ... -=-=-=-=-=-=-=-=-=-"
python -m unittest -v tests.LibbyClientTests

# clean up
clear_test_data
