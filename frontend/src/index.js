import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
// import App from './App';  // Old WebSocket version
import App from './AppLiveKit';  // New LiveKit version

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);