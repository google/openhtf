module.exports = require("protobufjs").newBuilder({})['import']({
    "package": "openxtf",
    "messages": [
        {
            "name": "Assembly",
            "fields": [
                {
                    "rule": "repeated",
                    "type": "Component",
                    "name": "component",
                    "id": 1
                },
                {
                    "rule": "repeated",
                    "type": "Edge",
                    "name": "edge",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "int32",
                    "name": "top_level_assembly",
                    "id": 3
                },
                {
                    "rule": "repeated",
                    "type": "Source",
                    "name": "source",
                    "id": 4
                }
            ],
            "messages": [
                {
                    "name": "Edge",
                    "fields": [
                        {
                            "rule": "required",
                            "type": "int32",
                            "name": "parent",
                            "id": 1
                        },
                        {
                            "rule": "required",
                            "type": "int32",
                            "name": "child",
                            "id": 2
                        }
                    ]
                }
            ]
        },
        {
            "name": "Component",
            "fields": [
                {
                    "rule": "required",
                    "type": "string",
                    "name": "part_number",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "serial_number",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "ByLot",
                    "name": "lot",
                    "id": 3
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "sku",
                    "id": 4
                },
                {
                    "rule": "repeated",
                    "type": "string",
                    "name": "deviation",
                    "id": 5
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "description",
                    "id": 6
                },
                {
                    "rule": "repeated",
                    "type": "Attribute",
                    "name": "attribute",
                    "id": 7
                }
            ],
            "oneofs": {
                "id": [
                    2,
                    3
                ]
            },
            "messages": [
                {
                    "name": "Attribute",
                    "fields": [
                        {
                            "rule": "required",
                            "type": "string",
                            "name": "key",
                            "id": 1
                        },
                        {
                            "rule": "optional",
                            "type": "int64",
                            "name": "as_int",
                            "id": 2
                        },
                        {
                            "rule": "optional",
                            "type": "string",
                            "name": "as_string",
                            "id": 3
                        },
                        {
                            "rule": "optional",
                            "type": "bytes",
                            "name": "as_bytes",
                            "id": 4
                        }
                    ],
                    "oneofs": {
                        "value": [
                            2,
                            3,
                            4
                        ]
                    }
                },
                {
                    "name": "ByLot",
                    "fields": [
                        {
                            "rule": "required",
                            "type": "string",
                            "name": "lot_number",
                            "id": 1
                        },
                        {
                            "rule": "optional",
                            "type": "string",
                            "name": "lot_index",
                            "id": 2
                        }
                    ]
                }
            ]
        },
        {
            "name": "Source",
            "fields": [
                {
                    "rule": "required",
                    "type": "int64",
                    "name": "timestamp_micros",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "TestRun",
                    "name": "test_run",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "URL",
                    "name": "url",
                    "id": 3
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "project",
                    "id": 4
                }
            ],
            "oneofs": {
                "kind": [
                    2,
                    3,
                    4
                ]
            },
            "messages": [
                {
                    "name": "TestRun",
                    "fields": [
                        {
                            "rule": "required",
                            "type": "string",
                            "name": "project",
                            "id": 1
                        },
                        {
                            "rule": "required",
                            "type": "bytes",
                            "name": "key",
                            "id": 2
                        }
                    ]
                },
                {
                    "name": "URL",
                    "fields": [
                        {
                            "rule": "required",
                            "type": "string",
                            "name": "url",
                            "id": 1
                        }
                    ]
                }
            ]
        },
        {
            "name": "Units",
            "fields": [],
            "enums": [
                {
                    "name": "UnitCode",
                    "values": [
                        {
                            "name": "NONE",
                            "id": 1
                        },
                        {
                            "name": "PERCENT",
                            "id": 2
                        },
                        {
                            "name": "NO_DIMENSION",
                            "id": 3
                        },
                        {
                            "name": "PIXEL",
                            "id": 4
                        },
                        {
                            "name": "PIXEL_LEVEL",
                            "id": 5
                        },
                        {
                            "name": "ROTATIONS_PER_MINUTE",
                            "id": 7
                        },
                        {
                            "name": "SECOND",
                            "id": 10
                        },
                        {
                            "name": "MHZ",
                            "id": 11
                        },
                        {
                            "name": "HERTZ",
                            "id": 12
                        },
                        {
                            "name": "MICROSECOND",
                            "id": 13
                        },
                        {
                            "name": "MILLIMETER",
                            "id": 21
                        },
                        {
                            "name": "CENTIMETER",
                            "id": 22
                        },
                        {
                            "name": "METER",
                            "id": 23
                        },
                        {
                            "name": "PER_METER",
                            "id": 24
                        },
                        {
                            "name": "MILLILITER",
                            "id": 25
                        },
                        {
                            "name": "CUBIC_FOOT",
                            "id": 26
                        },
                        {
                            "name": "DECIBEL",
                            "id": 30
                        },
                        {
                            "name": "DECIBEL_MW",
                            "id": 31
                        },
                        {
                            "name": "MICROAMP",
                            "id": 32
                        },
                        {
                            "name": "MILLIAMP",
                            "id": 33
                        },
                        {
                            "name": "MICROVOLT",
                            "id": 34
                        },
                        {
                            "name": "VOLT",
                            "id": 35
                        },
                        {
                            "name": "PICOFARAD",
                            "id": 36
                        },
                        {
                            "name": "COULOMB",
                            "id": 37
                        },
                        {
                            "name": "MILLIVOLT",
                            "id": 38
                        },
                        {
                            "name": "WATT",
                            "id": 39
                        },
                        {
                            "name": "AMPERE",
                            "id": 29
                        },
                        {
                            "name": "DEGREE_CELSIUS",
                            "id": 40
                        },
                        {
                            "name": "KELVIN",
                            "id": 41
                        },
                        {
                            "name": "BYTE",
                            "id": 50
                        },
                        {
                            "name": "MEGA_BYTES_PER_SECOND",
                            "id": 51
                        },
                        {
                            "name": "DEGREE",
                            "id": 60
                        },
                        {
                            "name": "RADIAN",
                            "id": 61
                        },
                        {
                            "name": "NEWTON",
                            "id": 70
                        },
                        {
                            "name": "CUBIC_CENTIMETER_PER_SEC",
                            "id": 80
                        },
                        {
                            "name": "MILLIBAR",
                            "id": 81
                        },
                        {
                            "name": "METRIC_FUCKTONNE",
                            "id": 100
                        },
                        {
                            "name": "IMPERIAL_FUCKTON",
                            "id": 101
                        }
                    ]
                }
            ]
        },
        {
            "name": "TestRun",
            "fields": [
                {
                    "rule": "required",
                    "type": "string",
                    "name": "dut_serial",
                    "id": 1
                },
                {
                    "rule": "required",
                    "type": "string",
                    "name": "tester_name",
                    "id": 2
                },
                {
                    "rule": "required",
                    "type": "TestInfo",
                    "name": "test_info",
                    "id": 3
                },
                {
                    "rule": "required",
                    "type": "Status",
                    "name": "test_status",
                    "id": 4
                },
                {
                    "rule": "optional",
                    "type": "int32",
                    "name": "cell_number",
                    "id": 15
                },
                {
                    "rule": "optional",
                    "type": "int64",
                    "name": "start_time_millis",
                    "id": 8
                },
                {
                    "rule": "optional",
                    "type": "int64",
                    "name": "end_time_millis",
                    "id": 9
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "run_name",
                    "id": 10
                },
                {
                    "rule": "repeated",
                    "type": "TestParameter",
                    "name": "test_parameters",
                    "id": 5
                },
                {
                    "rule": "repeated",
                    "type": "InformationParameter",
                    "name": "info_parameters",
                    "id": 6
                },
                {
                    "rule": "repeated",
                    "type": "TestRunLogMessage",
                    "name": "test_logs",
                    "id": 11
                },
                {
                    "rule": "repeated",
                    "type": "FailureCode",
                    "name": "failure_codes",
                    "id": 19
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "operator_name",
                    "id": 22
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "lot_number",
                    "id": 23
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "part_id",
                    "id": 24
                },
                {
                    "rule": "optional",
                    "type": "bool",
                    "name": "synthetic_dut",
                    "id": 25
                },
                {
                    "rule": "optional",
                    "type": "Assembly",
                    "name": "assembly",
                    "id": 26
                },
                {
                    "rule": "repeated",
                    "type": "Timing",
                    "name": "timings",
                    "id": 27
                },
                {
                    "rule": "repeated",
                    "type": "Phase",
                    "name": "phases",
                    "id": 28
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "framework_build",
                    "id": 17
                }
            ]
        },
        {
            "name": "TestInfo",
            "fields": [
                {
                    "rule": "required",
                    "type": "string",
                    "name": "name",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "description",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "version_string",
                    "id": 5
                }
            ]
        },
        {
            "name": "InformationParameter",
            "fields": [
                {
                    "rule": "required",
                    "type": "string",
                    "name": "name",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "bytes",
                    "name": "value_binary",
                    "id": 7
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "description",
                    "id": 3
                },
                {
                    "rule": "optional",
                    "type": "int64",
                    "name": "set_time_millis",
                    "id": 8
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "parameter_tag",
                    "id": 5
                },
                {
                    "rule": "optional",
                    "type": "InformationTag",
                    "name": "type",
                    "id": 4
                }
            ],
            "enums": [
                {
                    "name": "InformationTag",
                    "values": [
                        {
                            "name": "JPG",
                            "id": 2
                        },
                        {
                            "name": "PNG",
                            "id": 3
                        },
                        {
                            "name": "WAV",
                            "id": 4
                        },
                        {
                            "name": "BINARY",
                            "id": 5
                        },
                        {
                            "name": "TIMESERIES",
                            "id": 6
                        },
                        {
                            "name": "TEXT_UTF8",
                            "id": 7
                        }
                    ]
                }
            ]
        },
        {
            "name": "FailureCode",
            "fields": [
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "code",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "details",
                    "id": 2
                }
            ]
        },
        {
            "name": "TimeInfo",
            "fields": [
                {
                    "rule": "optional",
                    "type": "int64",
                    "name": "start_time_millis",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "int64",
                    "name": "end_time_millis",
                    "id": 2
                }
            ]
        },
        {
            "name": "Timing",
            "fields": [
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "name",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "description",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "TimeInfo",
                    "name": "time_info",
                    "id": 3
                }
            ]
        },
        {
            "name": "Phase",
            "fields": [
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "name",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "description",
                    "id": 2
                },
                {
                    "rule": "repeated",
                    "type": "string",
                    "name": "capabilities",
                    "id": 3
                },
                {
                    "rule": "optional",
                    "type": "TimeInfo",
                    "name": "timing",
                    "id": 4
                }
            ]
        },
        {
            "name": "TestRunLogMessage",
            "fields": [
                {
                    "rule": "optional",
                    "type": "int64",
                    "name": "timestamp_millis",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "log_message",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "logger_name",
                    "id": 3
                },
                {
                    "rule": "optional",
                    "type": "int32",
                    "name": "levelno",
                    "id": 4
                },
                {
                    "rule": "optional",
                    "type": "Level",
                    "name": "level",
                    "id": 7
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "log_source",
                    "id": 5
                },
                {
                    "rule": "optional",
                    "type": "int32",
                    "name": "lineno",
                    "id": 6
                }
            ],
            "enums": [
                {
                    "name": "Level",
                    "values": [
                        {
                            "name": "DEBUG",
                            "id": 10
                        },
                        {
                            "name": "INFO",
                            "id": 20
                        },
                        {
                            "name": "WARNING",
                            "id": 30
                        },
                        {
                            "name": "ERROR",
                            "id": 40
                        },
                        {
                            "name": "CRITICAL",
                            "id": 50
                        }
                    ]
                }
            ]
        },
        {
            "name": "TestParameter",
            "fields": [
                {
                    "rule": "required",
                    "type": "string",
                    "name": "name",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "Status",
                    "name": "status",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "description",
                    "id": 6
                },
                {
                    "rule": "optional",
                    "type": "bool",
                    "name": "important",
                    "id": 18
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "parameter_tag",
                    "id": 16
                },
                {
                    "rule": "optional",
                    "type": "double",
                    "name": "numeric_value",
                    "id": 11
                },
                {
                    "rule": "optional",
                    "type": "double",
                    "name": "numeric_minimum",
                    "id": 12
                },
                {
                    "rule": "optional",
                    "type": "double",
                    "name": "numeric_maximum",
                    "id": 13
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "text_value",
                    "id": 14
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "expected_text",
                    "id": 15
                },
                {
                    "rule": "optional",
                    "type": "bool",
                    "name": "is_optional",
                    "id": 17
                },
                {
                    "rule": "optional",
                    "type": "int64",
                    "name": "set_time_millis",
                    "id": 19
                },
                {
                    "rule": "optional",
                    "type": "Units.UnitCode",
                    "name": "unit_code",
                    "id": 20
                }
            ],
            "extensions": [
                5000,
                5199
            ]
        },
        {
            "name": "XTFFrontendEvent",
            "fields": [
                {
                    "rule": "required",
                    "type": "int32",
                    "name": "cell_number",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "serial_number",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "bool",
                    "name": "popup_result",
                    "id": 3
                }
            ]
        },
        {
            "name": "XTFStationResponse",
            "fields": [
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "station_name",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "framework_version",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "TestInfo",
                    "name": "test_info",
                    "id": 3
                },
                {
                    "rule": "repeated",
                    "type": "XTFCell",
                    "name": "cells",
                    "id": 4
                }
            ]
        },
        {
            "name": "XTFCell",
            "fields": [
                {
                    "rule": "required",
                    "type": "int32",
                    "name": "cell_number",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "TestRun",
                    "name": "test_run",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "Popup",
                    "name": "popup",
                    "id": 3
                }
            ]
        },
        {
            "name": "Popup",
            "fields": [
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "title",
                    "id": 1
                },
                {
                    "rule": "optional",
                    "type": "string",
                    "name": "content",
                    "id": 2
                },
                {
                    "rule": "optional",
                    "type": "PopupStyle",
                    "name": "style",
                    "id": 3
                }
            ],
            "enums": [
                {
                    "name": "PopupStyle",
                    "values": [
                        {
                            "name": "CONFIRM",
                            "id": 1
                        },
                        {
                            "name": "YESNO",
                            "id": 2
                        }
                    ]
                }
            ]
        }
    ],
    "enums": [
        {
            "name": "Status",
            "values": [
                {
                    "name": "PASS",
                    "id": 1
                },
                {
                    "name": "FAIL",
                    "id": 2
                },
                {
                    "name": "ERROR",
                    "id": 3
                },
                {
                    "name": "RUNNING",
                    "id": 4
                },
                {
                    "name": "CREATED",
                    "id": 5
                },
                {
                    "name": "TIMEOUT",
                    "id": 6
                },
                {
                    "name": "ABORTED",
                    "id": 7
                },
                {
                    "name": "WAITING",
                    "id": 8
                },
                {
                    "name": "CONSUME",
                    "id": 10
                },
                {
                    "name": "RMA",
                    "id": 11
                },
                {
                    "name": "REWORK",
                    "id": 12
                },
                {
                    "name": "SCRAP",
                    "id": 13
                },
                {
                    "name": "DEBUG",
                    "id": 14
                }
            ]
        }
    ]
}).build();