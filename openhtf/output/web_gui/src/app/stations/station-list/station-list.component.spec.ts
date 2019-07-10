/**
 * Tests for station-list.component.ts.
 */

import { Component } from '@angular/core';
import { async, ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable } from 'rxjs/Observable';
import { Subject } from 'rxjs/Subject';

import { ConfigService } from '../../core/config.service';
import { StationStatus } from '../../shared/models/station.model';
import { ObjectToSortedValuesPipe } from '../../shared/object-to-sorted-values.pipe';
import { StatusToTextPipe } from '../../shared/status-pipes';
import { TimeService } from '../../shared/time.service';

import { DashboardService } from './dashboard.service';
import { StationListComponent } from './station-list.component';

const hostTemplate = `
    <htf-station-list (onSelectStation)="onSelectStation($event)">
    </htf-station-list>`;

@Component({
  selector: 'unused',
  template: hostTemplate,
})
class StationListTestComponent {
  selectedStation;
  onSelectStation(event) {
    this.selectedStation = event.station;
  }
}

const mockConfig = {
  dashboardEnabled: true
};

class MockConfigService {
  private config = mockConfig;

  get dashboardEnabled() {
    return this.config.dashboardEnabled;
  }
}

class MockDashboardService {
  private stations = [];

  hasError = false;
  isSubscribing = false;
  messages = new Subject();
  subscribe = jasmine.createSpy('subscribe');
  unsubscribe = jasmine.createSpy('unsubscribe');

  getStations() {
    return this.stations;
  }

  registerMockStation(station) {
    this.stations.push(station);
    this.messages.next({});
  }
}

class MockTimeService {
  observable = Observable.of(1);
}

describe('station list component', () => {
  let fixture: ComponentFixture<StationListTestComponent>;
  let element: HTMLElement;
  let hostComponent: StationListTestComponent;
  let mockDashboardService: MockDashboardService;

  const mockStation = {
    label: 'station1.example.com:12000',
    status: StationStatus.online,
  };
  const mockUnreachableStation = {
    label: 'station2.example.com:12000',
    status: StationStatus.unreachable,
  };

  function initialize() {
    fixture = TestBed.createComponent(StationListTestComponent);
    const debugElement = fixture.debugElement;

    element = fixture.nativeElement;
    hostComponent = fixture.componentInstance;
    // tslint:disable-next-line:no-any force type conversion to mock type
    mockDashboardService = debugElement.injector.get(DashboardService) as any;
  }

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [
        ObjectToSortedValuesPipe,
        StationListComponent,
        StationListTestComponent,
        StatusToTextPipe,
      ],
      providers: [
        {provide: ConfigService, useClass: MockConfigService},
        {provide: DashboardService, useClass: MockDashboardService},
        {provide: TimeService, useClass: MockTimeService},
      ],
    });
    TestBed.compileComponents();
  }));

  describe('when the dashboard is enabled', () => {
    beforeEach(() => {
      initialize();
      fixture.detectChanges();
    });

    it('should indicate when attempting to subscribe', () => {
      mockDashboardService.isSubscribing = true;
      fixture.detectChanges();
      expect(element.textContent).toContain('Loading…');
    });

    it('should indicate a subscription error', () => {
      mockDashboardService.hasError = true;
      fixture.detectChanges();
      expect(element.textContent).toContain('Could not connect to the server.');
    });

    it('should indicate when successfully subscribed', () => {
      expect(element.textContent)
          .toContain('Connected to server. No stations found.');
      expect(mockDashboardService.subscribe)
          .toHaveBeenCalledWith(
              jasmine.any(Number), jasmine.any(Number), jasmine.any(Number));
    });

    it('should display available stations', () => {
      expect(element.textContent).toContain('No stations found.');

      mockDashboardService.registerMockStation(mockUnreachableStation);
      mockDashboardService.registerMockStation(mockStation);
      fixture.detectChanges();

      expect(element.textContent).not.toContain('No stations found.');
      expect(element.textContent).toContain(mockUnreachableStation.label);
      expect(element.textContent).toContain('Unreachable');
      expect(element.textContent).toContain(mockStation.label);
      expect(element.textContent).toContain('Online');
      expect(hostComponent.selectedStation).not.toBeDefined();
    });

    it('should unsubscribe when the component is destroyed', () => {
      fixture.detectChanges();
      expect(mockDashboardService.unsubscribe).not.toHaveBeenCalled();
      fixture.destroy();
      expect(mockDashboardService.unsubscribe).toHaveBeenCalledWith();
    });
  });

  describe('when the dashboard is disabled', () => {
    beforeEach(() => {
      mockConfig.dashboardEnabled = false;
      initialize();
      fixture.detectChanges();
    });

    it('should select the first station', () => {
      mockDashboardService.registerMockStation(mockStation);
      fixture.detectChanges();
      expect(hostComponent.selectedStation).toBe(mockStation);
    });

    afterEach(() => {
      mockConfig.dashboardEnabled = true;
    });
  });
});
