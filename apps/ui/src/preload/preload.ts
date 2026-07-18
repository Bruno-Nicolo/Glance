import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('glance', {
  getStatus: () => ipcRenderer.invoke('glance:getStatus'),
  getSettings: () => ipcRenderer.invoke('glance:getSettings'),
  updateSettings: (update: unknown) => ipcRenderer.invoke('glance:updateSettings', update),
  startTracking: () => ipcRenderer.invoke('glance:startTracking'),
  stopTracking: () => ipcRenderer.invoke('glance:stopTracking'),
  createCalibrationSession: (request: unknown) => ipcRenderer.invoke('glance:createCalibrationSession', request),
  submitCalibrationSamples: (sessionId: string, request: unknown) => (
    ipcRenderer.invoke('glance:submitCalibrationSamples', sessionId, request)
  ),
  completeCalibrationSession: (sessionId: string) => (
    ipcRenderer.invoke('glance:completeCalibrationSession', sessionId)
  ),
  cancelCalibrationSession: (sessionId: string) => ipcRenderer.invoke('glance:cancelCalibrationSession', sessionId),
  quitGlance: () => ipcRenderer.invoke('glance:quitGlance'),
});
