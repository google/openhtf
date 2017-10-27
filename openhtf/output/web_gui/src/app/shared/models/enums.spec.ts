import { MeasurementStatus } from './measurement.model';
import { PhaseStatus } from './phase.model';
import { StationStatus } from './station.model';
import { TestStatus } from './test-state.model';

const enumTypes = [MeasurementStatus, PhaseStatus, StationStatus, TestStatus];

function getEnumNames(enumType) {
  return Object.keys(enumType)
      .map(key => enumType[key])
      .filter(value => typeof value === 'string');
}

function getEnumValues(enumType) {
  return Object.keys(enumType)
      .map(key => enumType[key])
      .filter(value => typeof value === 'number');
}

describe('status enums', () => {
  it('should not overlap with one another', () => {
    const nameCount = enumTypes.reduce((nameCountAcc, enumType) => {
      return nameCountAcc + getEnumNames(enumType).length;
    }, 0);
    const valueCount = new Set(enumTypes.reduce((valuesListAcc, enumType) => {
                         return valuesListAcc.concat(getEnumValues(enumType));
                       }, [])).size;
    expect(nameCount).toEqual(valueCount);
  });
});
