/**
 * A log record of a test.
 */

export const logLevels = {
  debug: 10,
  info: 20,
  warning: 30,
  error: 40,
  critical: 50,
};

export class LogRecord {
  level: number;
  lineNumber: number;
  loggerName: string;
  message: string;
  source: string;
  timestampMillis: number;

  // Using the class as the interface for its own constructor allows us to call
  // the constructor in named-argument style.
  constructor(params: LogRecord) {
    Object.assign(this, params);
  }
}
