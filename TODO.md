## Code Structure
It would be really good to restructure the code to mirror the core abstractions
we identify in the README.md file. For example:
  
  * openhtf
    * configuration
    * execution
      * test_start
      * executor
      * htftest
      * phase_manager
      * test_manager
    * hardware
      * usb
    * io
      * frontend
      * http_handler
      * proto
      * rundata
      * test_record
      * testrun_adapter
      * user_input
    * util
      * data
      * exceptions (move to top level?)
      * file_watcher
      * geneology
      * htflogger
      * log_persistor
      * openhtf_stubs
      * measurements
      * threads
      * timeouts
      * utils (misc?)
