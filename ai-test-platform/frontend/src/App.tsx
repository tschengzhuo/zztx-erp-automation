import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './layouts/MainLayout';
import Dashboard from './pages/Dashboard';
import RequirementList from './pages/RequirementList';
import RequirementDetail from './pages/RequirementDetail';
import TestPointView from './pages/TestPointView';
import CaseView from './pages/CaseView';

const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="requirements" element={<RequirementList />} />
        <Route path="requirements/:id" element={<RequirementDetail />} />
        <Route path="requirements/:id/test-points" element={<TestPointView />} />
        <Route path="requirements/:id/cases" element={<CaseView />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
};

export default App;
