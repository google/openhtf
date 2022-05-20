/**
 * Tests for station.component.ts.
 */

import {Component, DebugElement, Input} from '@angular/core';
import {ComponentFixture, TestBed, waitForAsync} from '@angular/core/testing';

import {ConfigService} from '../../core/config.service';
import {Station, StationStatus} from '../../shared/models/station.model';
import {TestState} from '../../shared/models/test-state.model';
import {TimeAgoPipe} from '../../shared/time-ago.pipe';

import {StationComponent} from './station.component';
import {StationService} from './station.service';

// Selectors for components used in the station component template which take
// a single test state as input.
const testWidgets = [
  'htf-attachments',
  'htf-logs',
  'htf-phase-list',
  'htf-test-summary',
  'htf-abort-test-plug',
  'htf-assembly-plug',
  'htf-camera-demo-plug',
  'htf-notifications-plug',
  'htf-operator-plug',
  'htf-user-input-plug',
  'laser-ybr-alignment-plug',
];

function makeTestWidgetComponentStub(selector: string) {
  const template = `<div *ngIf="test">${selector}({{ test.dutId }})</div>`;
  @Component({selector, template})
  class TestWidgetComponentStub {
    @Input() test: TestState;
  }
  return TestWidgetComponentStub;
}

const testWidgetStubs = testWidgets.map(makeTestWidgetComponentStub);

@Component({
  selector: 'htf-history',
  template: '<div *ngIf="test">htf-history({{ test.dutId }})</div>',
})
class HistoryComponentStub {
  @Input() selectedTest: TestState;
  @Input() station: Station;
}

@Component({
  selector: 'unused',
  template: '<htf-station [selectedStation]="station"></htf-station>',
})
class HostComponent {
  station = new Station({
    cell: null,
    host: 'localhost',
    hostPort: 'localhost:12000',
    label: 'mock-station-id',
    port: '12000',
    stationId: 'mock-station-id',
    status: StationStatus.online,
    testDescription: null,
    testName: null,
  });
}

const mockConfig = {
  dashboardEnabled: true
};

class MockStationService {
  hasError = false;
  isSubscribing = false;
  subscribe = jasmine.createSpy('subscribe');
  unsubscribe = jasmine.createSpy('unsubscribe');
  test = null;

  getTest() {
    return this.test;
  }
}

describe('station component', () => {
  let fixture: ComponentFixture<HostComponent>;
  let element: HTMLElement;
  let debugElement: DebugElement;
  let hostComponent: HostComponent;
  let mockStationService: MockStationService;
  let mockActiveTest: {dutId: string};

  function initialize() {
    fixture = TestBed.createComponent(HostComponent);
    debugElement = fixture.debugElement;
    element = fixture.nativeElement;
    hostComponent = fixture.componentInstance;

    // tslint:disable-next-line:no-any force type conversion to mock type
    mockStationService = debugElement.injector.get(StationService) as any;

    mockActiveTest = {dutId: 'active-dut-id'};
  }

  beforeEach(waitForAsync(() => {
    TestBed.configureTestingModule({
      declarations: (testWidgetStubs as Array<{}>).concat([
        HistoryComponentStub,
        StationComponent,
        HostComponent,
        TimeAgoPipe,
      ]),
      providers: [
        {provide: ConfigService, useValue: mockConfig},
        {provide: StationService, useClass: MockStationService},
      ],
    });
    TestBed.compileComponents();
  }));

  beforeEach(() => {
    initialize();
    fixture.detectChanges();
  });

  it('should indicate when attempting to subscribe', () => {
    mockStationService.isSubscribing = true;
    fixture.detectChanges();
    expect(element.textContent).toContain('Status: Offline');
  });

  it('should indicate a subscription error', () => {
    mockStationService.hasError = true;
    fixture.detectChanges();
    expect(element.textContent).toContain('Status: Offline');
  });

  it('should indicate when successfully subscribed', () => {
    expect(element.textContent).toContain('mock-station-id');
    expect(element.textContent).toContain('Status: Connected');
    expect(mockStationService.subscribe)
        .toHaveBeenCalledWith(
            hostComponent.station, jasmine.any(Number), jasmine.any(Number),
            jasmine.any(Number));
  });

  it('should render widgets and pass the active test to them', () => {
    mockStationService.test = mockActiveTest;
    fixture.detectChanges();
    for (const selector of testWidgets) {
      expect(element.textContent).toContain(`${selector}(active-dut-id)`);
    }
  });

  it('should unsubscribe when the component is destroyed', () => {
    fixture.detectChanges();
    expect(mockStationService.unsubscribe).not.toHaveBeenCalled();
    fixture.destroy();
    expect(mockStationService.unsubscribe).toHaveBeenCalledWith();
  });
});
