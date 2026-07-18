import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('glance', {
  getStatus: () => ipcRenderer.invoke('glance:getStatus'),
  getSettings: () => ipcRenderer.invoke('glance:getSettings'),
  updateSettings: (update: unknown) => ipcRenderer.invoke('glance:updateSettings', update),
  startTracking: () => ipcRenderer.invoke('glance:startTracking'),
  stopTracking: () => ipcRenderer.invoke('glance:stopTracking'),
  quitGlance: () => ipcRenderer.invoke('glance:quitGlance'),
});
