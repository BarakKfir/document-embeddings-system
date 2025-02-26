import React, { useState, useEffect } from 'react';
import { Bar, Line } from 'recharts';
import { Bell, Check, Clock, AlertTriangle, RefreshCw, Play, ChevronDown } from 'lucide-react';

// Dashboard layout for the document sync management system
const DocumentSyncDashboard = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [syncJobs, setSyncJobs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedSource, setSelectedSource] = useState('all');
  const [syncStats, setSyncStats] = useState({
    completed: 0,
    failed: 0,
    running: 0,
    pending: 0
  });

  // Fetch sync jobs data
  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      try {
        // This would be a real API call in production
        const response = await fetch('/api/sync/jobs');
        const data = await response.json();
        
        // Process the data
        setSyncJobs(data.jobs);
        
        // Calculate statistics
        const stats = {
          completed: 0,
          failed: 0,
          running: 0,
          pending: 0
        };
        
        data.jobs.forEach(job => {
          stats[job.status]++;
        });
        
        setSyncStats(stats);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchData();
    
    // Set up polling interval
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  // Sample data for charts
  const syncTrendData = [
    { date: '02/20', successful: 5, failed: 1 },
    { date: '02/21', successful: 6, failed: 0 },
    { date: '02/22', successful: 4, failed: 2 },
    { date: '02/23', successful: 7, failed: 1 },
    { date: '02/24', successful: 8, failed: 0 },
    { date: '02/25', successful: 6, failed: 1 },
    { date: '02/26', successful: 9, failed: 0 },
  ];
  
  const documentStatsBySource = [
    { name: 'Admin Guides', processed: 1245, failed: 23 },
    { name: 'SKs', processed: 3678, failed: 42 },
    { name: 'MITRE', processed: 854, failed: 5 },
    { name: 'CPR Blogs', processed: 427, failed: 8 },
    { name: 'Jira', processed: 1892, failed: 32 },
  ];

  // Filter sync jobs based on selected source
  const filteredJobs = selectedSource === 'all'
    ? syncJobs
    : syncJobs.filter(job => job.source === selectedSource);

  // Handler for starting a new sync
  const handleStartSync = (source) => {
    // This would be a real API call in production
    console.log(`Starting sync for ${source}`);
  };

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-blue-800 text-white shadow">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-bold">Document Embeddings & Indexing Management</h1>
          <div className="flex items-center space-x-4">
            <button className="bg-blue-700 hover:bg-blue-600 px-3 py-2 rounded-md flex items-center">
              <RefreshCw size={16} className="mr-2" />
              Refresh
            </button>
            <button className="bg-blue-700 hover:bg-blue-600 px-3 py-2 rounded-md">
              <Bell size={18} />
            </button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white shadow">
        <div className="container mx-auto px-4">
          <div className="flex space-x-8">
            <button
              className={`py-4 px-2 border-b-2 ${activeTab === 'dashboard' ? 'border-blue-500 text-blue-500' : 'border-transparent'}`}
              onClick={() => setActiveTab('dashboard')}
            >
              Dashboard
            </button>
            <button
              className={`py-4 px-2 border-b-2 ${activeTab === 'jobs' ? 'border-blue-500 text-blue-500' : 'border-transparent'}`}
              onClick={() => setActiveTab('jobs')}
            >
              Sync Jobs
            </button>
            <button
              className={`py-4 px-2 border-b-2 ${activeTab === 'documents' ? 'border-blue-500 text-blue-500' : 'border-transparent'}`}
              onClick={() => setActiveTab('documents')}
            >
              Documents
            </button>
            <button
              className={`py-4 px-2 border-b-2 ${activeTab === 'settings' ? 'border-blue-500 text-blue-500' : 'border-transparent'}`}
              onClick={() => setActiveTab('settings')}
            >
              Settings
            </button>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="container mx-auto px-4 py-6">
          {/* Dashboard Tab */}
          {activeTab === 'dashboard' && (
            <div>
              {/* Stats Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
                <div className="bg-white rounded-lg shadow p-6">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-gray-500 text-sm">Completed Syncs</p>
                      <h2 className="text-2xl font-bold text-blue-600">{syncStats.completed}</h2>
                    </div>
                    <div className="bg-blue-100 p-3 rounded-full">
                      <Check className="text-blue-500" size={24} />
                    </div>
                  </div>
                </div>
                <div className="bg-white rounded-lg shadow p-6">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-gray-500 text-sm">Running Syncs</p>
                      <h2 className="text-2xl font-bold text-yellow-600">{syncStats.running}</h2>
                    </div>
                    <div className="bg-yellow-100 p-3 rounded-full">
                      <Clock className="text-yellow-500" size={24} />
                    </div>
                  </div>
                </div>
                <div className="bg-white rounded-lg shadow p-6">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-gray-500 text-sm">Pending Syncs</p>
                      <h2 className="text-2xl font-bold text-indigo-600">{syncStats.pending}</h2>
                    </div>
                    <div className="bg-indigo-100 p-3 rounded-full">
                      <Clock className="text-indigo-500" size={24} />
                    </div>
                  </div>
                </div>
                <div className="bg-white rounded-lg shadow p-6">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-gray-500 text-sm">Failed Syncs</p>
                      <h2 className="text-2xl font-bold text-red-600">{syncStats.failed}</h2>
                    </div>
                    <div className="bg-red-100 p-3 rounded-full">
                      <AlertTriangle className="text-red-500" size={24} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Charts */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                <div className="bg-white rounded-lg shadow p-6">
                  <h3 className="text-lg font-semibold mb-4">Sync Success Trend</h3>
                  <div className="h-64">
                    <Line
                      data={syncTrendData}
                      margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                    >
                      {/* Line chart elements would go here */}
                    </Line>
                  </div>
                </div>
                <div className="bg-white rounded-lg shadow p-6">
                  <h3 className="text-lg font-semibold mb-4">Documents Processed by Source</h3>
                  <div className="h-64">
                    <Bar
                      data={documentStatsBySource}
                      margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                    >
                      {/* Bar chart elements would go here */}
                    </Bar>
                  </div>
                </div>
              </div>

              {/* Recent Jobs */}
              <div className="bg-white rounded-lg shadow">
                <div className="border-b p-4 flex justify-between items-center">
                  <h3 className="text-lg font-semibold">Recent Sync Jobs</h3>
                  <button 
                    className="flex items-center text-blue-500 hover:text-blue-700"
                    onClick={() => setActiveTab('jobs')}
                  >
                    View All
                    <ChevronDown size={16} className="ml-1" />
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Source</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Progress</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Documents</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Started</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {isLoading ? (
                        <tr>
                          <td colSpan="6" className="px-6 py-4 text-center">Loading...</td>
                        </tr>
                      ) : syncJobs.length === 0 ? (
                        <tr>
                          <td colSpan="6" className="px-6 py-4 text-center">No sync jobs found</td>
                        </tr>
                      ) : (
                        syncJobs.slice(0, 5).map((job) => (
                          <tr key={job.id}>
                            <td className="px-6 py-4 whitespace-nowrap">{job.source}</td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                                ${job.status === 'completed' ? 'bg-green-100 text-green-800' : 
                                  job.status === 'running' ? 'bg-yellow-100 text-yellow-800' : 
                                  job.status === 'pending' ? 'bg-blue-100 text-blue-800' : 
                                  'bg-red-100 text-red-800'}`}>
                                {job.status}
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="w-full bg-gray-200 rounded h-2">
                                <div 
                                  className="bg-blue-600 h-2 rounded" 
                                  style={{ width: `${job.progress}%` }}
                                ></div>
                              </div>
                              <span className="text-xs text-gray-500">{job.progress}%</span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              {job.documents_success} / {job.documents_total}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              {new Date(job.created_at).toLocaleString()}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                              <button className="text-blue-600 hover:text-blue-900 mr-3">View</button>
                              {job.status === 'completed' && !job.prod_ready && (
                                <button className="text-green-600 hover:text-green-900">Mark as Prod Ready</button>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Jobs Tab */}
          {activeTab === 'jobs' && (
            <div>
              <div className="bg-white rounded-lg shadow mb-6">
                <div className="border-b p-4 flex justify-between items-center">
                  <h3 className="text-lg font-semibold">Start New Sync</h3>
                </div>
                <div className="p-4">
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                    {['admin_guides', 'secure_knowledge', 'mitre', 'cpr_blogs', 'jira_tickets'].map((source) => (
                      <button
                        key={source}
                        className="bg-blue-100 hover:bg-blue-200 text-blue-800 py-3 px-4 rounded-lg flex flex-col items-center justify-center"
                        onClick={() => handleStartSync(source)}
                      >
                        <Play size={24} className="mb-2" />
                        <span className="text-sm font-medium">
                          {source === 'admin_guides' ? 'Admin Guides' :
                           source === 'secure_knowledge' ? 'Secure Knowledge' :
                           source === 'mitre' ? 'MITRE' :
                           source === 'cpr_blogs' ? 'CPR Blogs' : 'Jira Tickets'}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-lg shadow">
                <div className="border-b p-4 flex justify-between items-center">
                  <h3 className="text-lg font-semibold">All Sync Jobs</h3>
                  <div className="flex items-center">
                    <label htmlFor="source-filter" className="mr-2 text-sm text-gray-600">Filter by Source:</label>
                    <select
                      id="source-filter"
                      className="border rounded py-1 px-2"
                      value={selectedSource}
                      onChange={(e) => setSelectedSource(e.target.value)}
                    >
                      <option value="all">All Sources</option>
                      <option value="admin_guides">Admin Guides</option>
                      <option value="secure_knowledge">Secure Knowledge</option>
                      <option value="mitre">MITRE</option>
                      <option value="cpr_blogs">CPR Blogs</option>
                      <option value="jira_tickets">Jira Tickets</option>
                    </select>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Source</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Progress</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Documents</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Started</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Completed</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {isLoading ? (
                        <tr>
                          <td colSpan="7" className="px-6 py-4 text-center">Loading...</td>
                        </tr>
                      ) : filteredJobs.length === 0 ? (
                        <tr>
                          <td colSpan="7" className="px-6 py-4 text-center">No sync jobs found</td>
                        </tr>
                      ) : (
                        filteredJobs.map((job) => (
                          <tr key={job.id}>
                            <td className="px-6 py-4 whitespace-nowrap">{job.source}</td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                                ${job.status === 'completed' ? 'bg-green-100 text-green-800' : 
                                  job.status === 'running' ? 'bg-yellow-100 text-yellow-800' : 
                                  job.status === 'pending' ? 'bg-blue-100 text-blue-800' : 
                                  'bg-red-100 text-red-800'}`}>
                                {job.status}
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="w-full bg-gray-200 rounded h-2">
                                <div 
                                  className="bg-blue-600 h-2 rounded" 
                                  style={{ width: `${job.progress}%` }}
                                ></div>
                              </div>
                              <span className="text-xs text-gray-500">{job.progress}%</span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              {job.documents_success} / {job.documents_total}
                              {job.documents_failed > 0 && (
                                <span className="ml-2 text-red-500">({job.documents_failed} failed)</span>
                              )}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              {new Date(job.created_at).toLocaleString()}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              {job.completed_at ? new Date(job.completed_at).toLocaleString() : '-'}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                              <button className="text-blue-600 hover:text-blue-900 mr-3">View</button>
                              {job.status === 'completed' && !job.prod_ready && (
                                <button className="text-green-600 hover:text-green-900">Mark as Prod Ready</button>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Additional tab content would go here */}
        </div>
      </main>
    </div>
  );
};

export default DocumentSyncDashboard;
