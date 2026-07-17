import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('glance', {
  getStatus: () => ipcRenderer.invoke('glance:getStatus'),
  quitGlance: () => ipcRenderer.invoke('glance:quitGlance'),
});
