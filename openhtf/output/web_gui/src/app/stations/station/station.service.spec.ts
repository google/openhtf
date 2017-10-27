/**
 * Tests for station.service.ts.
 */

import { fakeAsync, tick } from '@angular/core/testing';
import { Observable } from 'rxjs/Observable';

import { PhaseStatus } from '../../shared/models/phase.model';
import { Station, StationStatus } from '../../shared/models/station.model';
import { TestState, TestStatus } from '../../shared/models/test-state.model';
import { MockSockJsInstance, MockSockJsService } from '../../shared/sock-js.service.mock';

import { StationService } from './station.service';

/**
 * Mock station objects.
 */

const mockStation = new Station({
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

const mockStation2 = new Station({
  cell: null,
  host: 'localhost',
  hostPort: 'localhost:12001',
  label: 'mock-station-id',
  port: '12001',
  stationId: 'mock-station-id',
  status: StationStatus.online,
  testDescription: null,
  testName: null,
});

/**
 * Mock websocket data.
 */

const createMockTestStateResponse = (testId: string, status: string) => {
  return {
    state: {
      plugs: {},
      running_phase_state: {
        attachments: {},
        descriptor_id: 2,
        measurements: {},
      },
      status,
      test_record: {
        log_records: [],
        metadata: {},
        outcome: status === 'COMPLETED' ? 'PASS' : undefined,
        phases: [{
          attachments: {},
          descriptor_id: 1,
          measurements: {},
        }],
      },
    },
    test_uid: testId,
    type: 'update',
  };
};

/**
 * Mock phase descriptor data.
 */

const makeMockPhaseDescriptor = (descriptorId) => {
  return {
    id: descriptorId,
    name: 'Phase',
    measurements: [],
  };
};

const mockGetResponse = {
  json: () => {
    return {
      data: [
        makeMockPhaseDescriptor(1),
        makeMockPhaseDescriptor(2),
        makeMockPhaseDescriptor(3),
      ]
    };
  },
};

const mockGetPhasesDescriptors = Observable.of(mockGetResponse);

/**
 * Mock services.
 */

const mockHttpService = {
  get: jasmine.createSpy('get').and.returnValue(mockGetPhasesDescriptors),
};

const mockConfig = {
  dashboardEnabled: true
};

const mockFlashMessageService = {
  error: jasmine.createSpy('error'),
  warn: jasmine.createSpy('warn'),
};

const mockHistoryService = {
  prependItemFromTestState: jasmine.createSpy('prependItemFromTestState'),
};

/**
 * Test cases.
 */

describe('station service', () => {
  let mockSockJsInstance: MockSockJsInstance;
  let mockSockJsService: MockSockJsService;
  let stationService: StationService;

  const connectSuccessfully = () => {
    mockSockJsInstance.onopen();
  };

  const receiveMockMessage = (response: {}) => {
    mockSockJsInstance.onmessage({
      data: response,
    });
  };

  beforeEach(() => {
    // Set up SockJs mock.
    mockSockJsInstance = new MockSockJsInstance();
    mockSockJsService = new MockSockJsService();
    spyOn(mockSockJsService, 'sockJs').and.returnValue(mockSockJsInstance);

    stationService = new StationService(
        // tslint:disable-next-line:no-any pass mock in place of real service
        mockConfig as any, mockFlashMessageService as any,
        // tslint:disable-next-line:no-any pass mock in place of real service
        mockHistoryService as any, mockHttpService as any,
        // tslint:disable-next-line:no-any pass mock in place of real service
        mockSockJsService as any);
  });

  it('should connect to the station pubsub URL', () => {
    expect(mockSockJsService.sockJs).not.toHaveBeenCalled();
    expect(stationService.isSubscribing).toBe(false);
    expect(stationService.hasError).toBe(false);

    stationService.subscribe(mockStation);

    const expectedUrl = `http://${mockStation.hostPort}/sub/station`;
    expect(mockSockJsService.sockJs).toHaveBeenCalledWith(expectedUrl);
    expect(stationService.isSubscribing).toBe(true);
    expect(stationService.hasError).toBe(false);
  });

  it('should receive and parse test information', fakeAsync(() => {
       stationService.subscribe(mockStation);

       expect(stationService.getTest(mockStation)).toBe(null);

       connectSuccessfully();
       receiveMockMessage(
           createMockTestStateResponse('mock-id-000', 'COMPLETED'));
       receiveMockMessage(
           createMockTestStateResponse('mock-id-001', 'RUNNING'));
       tick();

       expect(stationService.isSubscribing).toBe(false);
       expect(stationService.hasError).toBe(false);
       expect(stationService.getTest(mockStation)).not.toBe(null);

       // The API responses should be converted into TestState objects.
       const test: TestState = stationService.getTest(mockStation);
       expect(test.testId).toEqual('mock-id-001');
     }));

  it('should update a test state', fakeAsync(() => {
       stationService.subscribe(mockStation);
       connectSuccessfully();
       receiveMockMessage(
           createMockTestStateResponse('mock-id-000', 'RUNNING'));
       receiveMockMessage(
           createMockTestStateResponse('mock-id-000', 'COMPLETED'));
       tick();

       const test: TestState = stationService.getTest(mockStation);
       expect(test.status).toEqual(TestStatus.pass);
     }));

  it('should subscribe to a new station', fakeAsync(() => {
       stationService.subscribe(mockStation);
       connectSuccessfully();

       expect(stationService.getTest(mockStation2)).toBe(null);
       spyOn(mockSockJsInstance, 'close');

       stationService.subscribe(mockStation2);
       connectSuccessfully();
       receiveMockMessage(
           createMockTestStateResponse('mock-id-000', 'RUNNING'));
       tick();

       expect(stationService.getTest(mockStation2)).not.toBe(null);

       // Expect station service to unsubscribe from the first station.
       expect(mockSockJsInstance.close).toHaveBeenCalledWith();
     }));

  it('should get pending phases', fakeAsync(() => {
       mockHttpService.get.calls.reset();

       stationService.subscribe(mockStation);
       connectSuccessfully();
       receiveMockMessage(
           createMockTestStateResponse('mock-id-000', 'RUNNING'));
       tick();

       const test: TestState = stationService.getTest(mockStation);
       expect(test).not.toBe(null);
       expect(mockHttpService.get).toHaveBeenCalledWith(jasmine.any(String));
       expect(mockHttpService.get.calls.count()).toBe(1);
       expect(test.phases.length).toEqual(3);
       expect(test.phases[0].status).toEqual(PhaseStatus.pass);
       expect(test.phases[1].status).toEqual(PhaseStatus.running);
       expect(test.phases[2].status).toEqual(PhaseStatus.waiting);
     }));
});
