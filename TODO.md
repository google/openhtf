## Code Structure
It would be really good to restructure the code to mirror the core abstractions
we identify in the README.md file. For example:
  
  * openhtf
    
    * Test()
    * Measurement()
    * @measures()
    * @run_if()
    * @timeout()
    * attach()

    * config
    
    * exec
      * test_start
      * test_executor
      * htftest
      * phase_executor
    
    * hw
      * plugs
        * usb
    
    * io
      * frontend
      * http_handler
      * proto
      * rundata
      * records
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
