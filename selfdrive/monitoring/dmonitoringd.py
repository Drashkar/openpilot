#!/usr/bin/env python3
from cereal import car
from common.op_params import opParams
from common.params import Params
import cereal.messaging as messaging
from selfdrive.controls.lib.events import Events
from selfdrive.monitoring.driver_monitor import DriverStatus
from selfdrive.locationd.calibrationd import Calibration


def dmonitoringd_thread(sm=None, pm=None):
  if pm is None:
    pm = messaging.PubMaster(['driverMonitoringState'])

  if sm is None:
    sm = messaging.SubMaster(['driverState', 'liveCalibration', 'carState', 'controlsState', 'modelV2'], poll=['driverState'])

  driver_status = DriverStatus(rhd=Params().get_bool("IsRHD"))

  sm['liveCalibration'].calStatus = Calibration.INVALID
  sm['liveCalibration'].rpyCalib = [0, 0, 0]
  sm['carState'].buttonEvents = []
  sm['carState'].standstill = True

  v_cruise_last = 0
  driver_engaged = False

  # 10Hz <- dmonitoringmodeld
  while True:
    sm.update()

    if not sm.updated['driverState']:
      continue

    # Get interaction
    if sm.updated['carState']:
      v_cruise = sm['carState'].cruiseState.speed
      driver_engaged = len(sm['carState'].buttonEvents) > 0 or \
                        v_cruise != v_cruise_last or \
                        sm['carState'].steeringPressed or \
                        sm['carState'].gasPressed or \
                        opParams().get('not_visible_to_dm_cam')
      if driver_engaged:
        driver_status.update(Events(), True, sm['controlsState'].enabled, sm['carState'].standstill)
      v_cruise_last = v_cruise

    if sm.updated['modelV2']:
      driver_status.set_policy(sm['modelV2'])

    # Get data from dmonitoringmodeld
    events = Events()
    driver_status.get_pose(sm['driverState'], sm['liveCalibration'].rpyCalib, sm['carState'].vEgo, sm['controlsState'].enabled)

    # Block engaging after max number of distrations
    if driver_status.terminal_alert_cnt >= driver_status.settings._MAX_TERMINAL_ALERTS or \
       driver_status.terminal_time >= driver_status.settings._MAX_TERMINAL_DURATION:
      events.add(car.CarEvent.EventName.tooDistracted)

    # Update events from driver state
    driver_status.update(events, driver_engaged, sm['controlsState'].enabled, sm['carState'].standstill)

    # build driverMonitoringState packet
    dat = messaging.new_message('driverMonitoringState')
    dat.driverMonitoringState = {
      "events": events.to_msg(),
      "faceDetected": driver_status.face_detected,
      "isDistracted": driver_status.driver_distracted,
      "awarenessStatus": driver_status.awareness,
      "posePitchOffset": driver_status.pose.pitch_offseter.filtered_stat.mean(),
      "posePitchValidCount": driver_status.pose.pitch_offseter.filtered_stat.n,
      "poseYawOffset": driver_status.pose.yaw_offseter.filtered_stat.mean(),
      "poseYawValidCount": driver_status.pose.yaw_offseter.filtered_stat.n,
      "stepChange": driver_status.step_change,
      "awarenessActive": driver_status.awareness_active,
      "awarenessPassive": driver_status.awareness_passive,
      "isLowStd": driver_status.pose.low_std,
      "hiStdCount": driver_status.hi_stds,
      "isActiveMode": driver_status.active_monitoring_mode,
    }
    pm.send('driverMonitoringState', dat)

def main(sm=None, pm=None):
  dmonitoringd_thread(sm, pm)

if __name__ == '__main__':
  main()
