import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import { FiPlus, FiSend, FiPaperclip, FiTrash2, FiStopCircle, FiShare2, FiMoreVertical, FiDownload, FiCamera, FiRefreshCw, FiChevronDown, FiChevronUp } from 'react-icons/fi';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import ApiClient from './services/ApiClient';
import { v4 as uuidv4 } from 'uuid';

function App() {
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [contextMenu, setContextMenu] = useState(null);
  // Predefined test users for easier testing
  const TEST_USERS = [
    { id: 'test_user_dleader', name: 'Test User (Default)' },
    { id: 'dleader_test', name: 'DLeader Test' },
    { id: 'user_alice', name: 'Alice' },
    { id: 'user_bob', name: 'Bob' },
    { id: 'custom', name: 'Custom User ID' }
  ];

  // Get or create persistent user ID from localStorage
  const [userId, setUserId] = useState(() => {
    const storedUserId = localStorage.getItem('dleader_user_id');
    if (storedUserId) {
      return storedUserId;
    }
    // Default to test_user_dleader for testing
    const defaultUserId = 'test_user_dleader';
    localStorage.setItem('dleader_user_id', defaultUserId);
    return defaultUserId;
  });
  const [showUserSelector, setShowUserSelector] = useState(false);
  const [snapshots, setSnapshots] = useState([]);
  const [showSnapshots, setShowSnapshots] = useState(false);
  const [downloadUrls, setDownloadUrls] = useState(null);
  const [showSessionDetails, setShowSessionDetails] = useState(false);
  const [showThinkingProcess, setShowThinkingProcess] = useState(false);
  const [finalReport, setFinalReport] = useState(null); // eslint-disable-line no-unused-vars
  const [isTaskComplete, setIsTaskComplete] = useState(false);
  const [showQuerySidebar, setShowQuerySidebar] = useState(true);
  const [allQueries, setAllQueries] = useState([]);

  const chatContainerRef = useRef(null);
  const fileInputRef = useRef(null);
  const statusCheckInterval = useRef(null);
  const apiClient = useRef(new ApiClient(process.env.REACT_APP_API_URL || 'http://52.192.211.135:8001'));

  useEffect(() => {
    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages]);

  const loadSessions = async () => {
    const allSessions = await apiClient.current.getAllSessions(userId);
    // Merge multi-turn chats by grouping consecutive sessions
    const mergedSessions = mergeSessions(allSessions);
    setSessions(mergedSessions.reverse());
    // Extract all queries for sidebar
    extractAllQueries(mergedSessions);
  };

  const mergeSessions = (sessionList) => {
    if (!sessionList || sessionList.length === 0) return [];

    const merged = [];
    let currentGroup = null;

    sessionList.forEach((session, index) => {
      // Check if this session is part of a multi-turn conversation
      const isMultiTurn = session.query &&
        (session.query.toLowerCase().includes('continue') ||
         session.query.toLowerCase().includes('next') ||
         session.query.toLowerCase().includes('then') ||
         (index > 0 && isRelatedSession(sessionList[index - 1], session)));

      if (isMultiTurn && currentGroup) {
        // Add to current group
        currentGroup.queries = currentGroup.queries || [currentGroup.query];
        currentGroup.queries.push(session.query);
        currentGroup.multiTurn = true;
        currentGroup.sessions = currentGroup.sessions || [currentGroup.session_id];
        currentGroup.sessions.push(session.session_id);
      } else {
        // Start new group
        if (currentGroup) merged.push(currentGroup);
        currentGroup = { ...session };
      }
    });

    if (currentGroup) merged.push(currentGroup);
    return merged;
  };

  const isRelatedSession = (prevSession, currentSession) => {
    if (!prevSession || !currentSession) return false;

    // Check if sessions are close in time (within 30 minutes)
    const prevTime = new Date(prevSession.timestamp || prevSession.created_at);
    const currTime = new Date(currentSession.timestamp || currentSession.created_at);
    const timeDiff = Math.abs(currTime - prevTime) / (1000 * 60); // minutes

    return timeDiff < 30;
  };

  const extractAllQueries = (sessionList) => {
    const queries = [];
    sessionList.forEach((session) => {
      if (session.multiTurn && session.queries) {
        session.queries.forEach((q, idx) => {
          queries.push({
            query: q,
            sessionId: session.sessions ? session.sessions[idx] : session.session_id,
            timestamp: session.timestamp,
            turn: idx + 1,
            totalTurns: session.queries.length
          });
        });
      } else {
        queries.push({
          query: session.query,
          sessionId: session.session_id,
          timestamp: session.timestamp,
          turn: 1,
          totalTurns: 1
        });
      }
    });
    setAllQueries(queries);
  };

  const switchUser = (newUserId) => {
    if (newUserId === 'custom') {
      // Show custom input
      setShowUserSelector(true);
      return;
    }

    if (newUserId && newUserId !== userId) {
      localStorage.setItem('dleader_user_id', newUserId);
      setUserId(newUserId);
      setCurrentSessionId(null);
      setMessages([]);
      setSnapshots([]);
      setIsTaskComplete(false);
      setShowUserSelector(false);
      // Reload sessions for new user
      apiClient.current.getAllSessions(newUserId).then(sessions => {
        const mergedSessions = mergeSessions(sessions);
        setSessions(mergedSessions.reverse());
        extractAllQueries(mergedSessions);
      });
    }
  };

  const createNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setStatus(null);
    setUploadedFiles([]);
    setSnapshots([]);
    setIsTaskComplete(false);
    setFinalReport(null);
    setShowThinkingProcess(false);
    setShowSnapshots(false);
  };

  const selectSession = async (sessionId) => {
    setCurrentSessionId(sessionId);

    // Reset states when selecting a session
    setSnapshots([]);
    setIsTaskComplete(false);
    setFinalReport(null);
    setShowThinkingProcess(false);
    setShowSnapshots(false);

    // Try to get multiturn session history first
    const multiturnData = await apiClient.current.getSessionHistory(sessionId, userId);

    if (multiturnData && multiturnData.turns && multiturnData.turns.length > 0) {
      // Handle multi-turn session format
      const formattedMessages = [];
      multiturnData.turns.forEach(turn => {
        // Add user message
        formattedMessages.push({
          role: 'user',
          content: turn.user_message || turn.message || ''
        });
        // Add assistant response if exists
        if (turn.agent_response || turn.response) {
          formattedMessages.push({
            role: 'assistant',
            content: turn.agent_response || turn.response
          });
        }
      });
      setMessages(formattedMessages);

      // Check if the last turn is completed
      if (formattedMessages.length > 0) {
        const lastMessage = formattedMessages[formattedMessages.length - 1];
        if (lastMessage.role === 'assistant') {
          // Load snapshots and download URLs for completed sessions
          const lastTurn = multiturnData.turns[multiturnData.turns.length - 1];
          if (lastTurn && lastTurn.turn_id) {
            checkSnapshots(lastTurn.turn_id);
            checkDownloadUrls(lastTurn.turn_id);
          } else {
            checkSnapshots(sessionId);
            checkDownloadUrls(sessionId);
          }
        }
      }
    } else {
      // For single turn sessions or if multiturn fails, just load as a simple session
      // This might be a simple session that just shows in the list
      setMessages([]);
    }
  };

  const handleFileUpload = (e) => {
    const files = Array.from(e.target.files);
    setUploadedFiles([...uploadedFiles, ...files]);
  };

  const removeFile = (index) => {
    setUploadedFiles(uploadedFiles.filter((_, i) => i !== index));
  };

  const checkSnapshots = async (sessionId) => {
    const snapshotsData = await apiClient.current.getSnapshots(sessionId, userId);
    if (snapshotsData && snapshotsData.snapshots) {
      setSnapshots(snapshotsData.snapshots);
      // Automatically show snapshots when they're available during processing
      if (!isTaskComplete && snapshotsData.snapshots.length > 0) {
        setShowSnapshots(true);
      }
    }
  };

  const checkDownloadUrls = async (sessionId) => {
    const urls = await apiClient.current.getDownloadUrls(sessionId, userId);
    if (urls) {
      setDownloadUrls(urls);
    }
  };

  const checkStatus = useCallback(async (sessionId) => {
    const statusData = await apiClient.current.getStatus(sessionId, userId);

    if (statusData) {
      setStatus(statusData.status);

      // Check if task is complete using is_complete flag (like Gradio does)
      if (statusData.is_complete && statusData.status === 'completed') {
        // Get the structured JSON results for the final report
        const resultsData = await apiClient.current.getResults(sessionId, userId);

        let finalReportContent = statusData.response; // fallback to response
        if (resultsData && resultsData.content && resultsData.content.final_report) {
          // Use the clean final report from JSON results
          finalReportContent = resultsData.content.final_report;
        }

        setFinalReport(finalReportContent);
        setIsTaskComplete(true);
        setShowSnapshots(false); // Hide live snapshots
        setShowThinkingProcess(false); // Initially collapse thinking process

        setMessages(prev => {
          const newMessages = [...prev];
          if (newMessages[newMessages.length - 1]?.role !== 'assistant') {
            newMessages.push({
              role: 'assistant',
              content: finalReportContent,
              isComplete: true
            });
          }
          return newMessages;
        });
        setIsLoading(false);
        clearInterval(statusCheckInterval.current);
        loadSessions();
        checkDownloadUrls(sessionId);
      } else if (statusData.is_complete && (statusData.status === 'failed' || statusData.status === 'error')) {
        setIsTaskComplete(true);
        setShowSnapshots(false);
        setMessages(prev => {
          const newMessages = [...prev];
          if (newMessages[newMessages.length - 1]?.role !== 'assistant') {
            newMessages.push({
              role: 'assistant',
              content: statusData.error || 'Task failed. Please try again.'
            });
          }
          return newMessages;
        });
        setIsLoading(false);
        clearInterval(statusCheckInterval.current);
      } else if (statusData.partial_response) {
        setMessages(prev => {
          const newMessages = [...prev];
          const lastMessage = newMessages[newMessages.length - 1];
          if (lastMessage?.role === 'assistant') {
            lastMessage.content = statusData.partial_response;
          } else {
            newMessages.push({
              role: 'assistant',
              content: statusData.partial_response
            });
          }
          return newMessages;
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() && uploadedFiles.length === 0) return;

    const userMessage = inputMessage.trim();
    setInputMessage('');
    setMessages([...messages, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    // Reset completion state for new messages
    setIsTaskComplete(false);
    setFinalReport(null);
    setShowThinkingProcess(false);
    setSnapshots([]);

    let sessionIdToCheck;
    if (currentSessionId && messages.length > 0) {
      // Continue existing multi-turn session
      const result = await apiClient.current.continueSession(
        currentSessionId,
        userMessage,
        'en',
        userId,
        uploadedFiles
      );
      if (result && result.turn_session_id) {
        // Use the turn_session_id for checking this specific turn's status
        sessionIdToCheck = result.turn_session_id;
        // Keep the original session_id as current
        // currentSessionId remains unchanged
      }
    } else {
      // Start new session
      const sessionId = await apiClient.current.submitRequest(
        userMessage,
        'en',
        userId,
        uploadedFiles
      );
      if (sessionId) {
        setCurrentSessionId(sessionId);
        sessionIdToCheck = sessionId;
      }
    }

    setUploadedFiles([]);

    if (sessionIdToCheck) {
      statusCheckInterval.current = setInterval(() => {
        checkStatus(sessionIdToCheck);
        checkSnapshots(sessionIdToCheck);
      }, 5000); // Check every 5 seconds
    } else {
      setIsLoading(false);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Failed to submit request. Please check if the server is running.'
      }]);
    }
  };

  const handleStopTask = async () => {
    if (currentSessionId) {
      await apiClient.current.stopTask(currentSessionId, userId);
      clearInterval(statusCheckInterval.current);
      setIsLoading(false);
      setStatus('stopped');
    }
  };

  const handleShareSession = async () => {
    if (currentSessionId) {
      const downloadUrl = await apiClient.current.getDownloadUrl(currentSessionId, userId);
      if (downloadUrl) {
        window.open(downloadUrl, '_blank');
      }
    }
  };

  const handleDownloadZip = async () => {
    if (currentSessionId) {
      const downloadUrl = await apiClient.current.getDownloadUrl(currentSessionId, userId);
      if (downloadUrl) {
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = `session_${currentSessionId}.zip`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    }
  };

  const formatTimestamp = (timestamp) => {
    try {
      const dt = new Date(timestamp);
      return dt.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const handleDeleteSession = async (sessionId, e) => {
    e.stopPropagation();
    const confirmed = window.confirm('Are you sure you want to delete this chat?');
    if (confirmed) {
      await apiClient.current.deleteSession(sessionId, userId);
      if (sessionId === currentSessionId) {
        createNewChat();
      }
      loadSessions();
    }
  };

  const handleContextMenu = (e, sessionId) => {
    e.preventDefault();
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      sessionId
    });
  };

  const closeContextMenu = () => {
    setContextMenu(null);
  };

  useEffect(() => {
    const handleClickOutside = (e) => {
      // Close context menu
      closeContextMenu();

      // Close user dropdown if clicked outside
      if (!e.target.closest('.user-selector-container')) {
        setShowUserSelector(false);
      }
    };

    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  return (
    <div className="app">
      <div className="sidebar">
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={createNewChat}>
            <FiPlus size={18} />
            New Chat
          </button>
          <div className="user-selector-container">
            <div className="user-info">
              <span className="user-id-label">User: {userId}</span>
              <button
                className="user-selector-btn"
                onClick={() => setShowUserSelector(!showUserSelector)}
                title="Switch User"
              >
                Switch User ▼
              </button>
            </div>

            {showUserSelector && (
              <div className="user-dropdown">
                <div className="user-dropdown-header">
                  <strong>Select User:</strong>
                </div>
                {TEST_USERS.map(user => (
                  <button
                    key={user.id}
                    className={`user-option ${userId === user.id ? 'active' : ''}`}
                    onClick={() => {
                      if (user.id === 'custom') {
                        const customId = prompt('Enter custom user ID:');
                        if (customId && customId.trim()) {
                          switchUser(customId.trim());
                        }
                      } else {
                        switchUser(user.id);
                      }
                    }}
                  >
                    {user.name}
                    {userId === user.id && ' ✓'}
                  </button>
                ))}
                <div className="user-dropdown-footer">
                  <button
                    className="generate-new-btn"
                    onClick={() => {
                      const newUserId = `user_${uuidv4()}`;
                      switchUser(newUserId);
                    }}
                  >
                    Generate New Random User
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="sidebar-content">
          <div className="session-list">
            {sessions.map((session) => (
              <button
                key={session.session_id}
                className={`session-item ${currentSessionId === session.session_id ? 'active' : ''}`}
                onClick={() => selectSession(session.session_id)}
                onContextMenu={(e) => handleContextMenu(e, session.session_id)}
              >
                {session.first_message || session.session_id}
                <button
                  className="delete-btn"
                  onClick={(e) => handleDeleteSession(session.session_id, e)}
                >
                  <FiTrash2 size={14} />
                </button>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="main-content">
        {currentSessionId && (
          <div className="session-toolbar">
            <button
              className="toolbar-btn"
              onClick={() => setShowSnapshots(!showSnapshots)}
              title="View Snapshots"
            >
              <FiCamera size={18} />
              <span>Snapshots ({snapshots.length})</span>
              {showSnapshots ? <FiChevronUp size={16} /> : <FiChevronDown size={16} />}
            </button>
            <button
              className="toolbar-btn"
              onClick={() => checkSnapshots(currentSessionId)}
              title="Refresh Snapshots"
            >
              <FiRefreshCw size={18} />
              <span>Refresh</span>
            </button>
            {downloadUrls && (
              <button
                className="toolbar-btn"
                onClick={handleDownloadZip}
                title="Download Session ZIP"
              >
                <FiDownload size={18} />
                <span>Download ZIP</span>
              </button>
            )}
            <button
              className="toolbar-btn"
              onClick={() => setShowSessionDetails(!showSessionDetails)}
              title="Session Details"
            >
              <FiMoreVertical size={18} />
              <span>Details</span>
            </button>
          </div>
        )}

        {showSnapshots && snapshots.length > 0 && !isTaskComplete && (
          <div className="snapshots-panel">
            <div className="snapshots-header">
              <h3>📸 All Snapshots ({snapshots.length} total)</h3>
              <p className="snapshots-info">All snapshots are displayed below in chronological order. Scroll down to view complete content.</p>
            </div>
            <div className="snapshots-list">
              {snapshots.map((snapshot, index) => {
                const thinkingContent = snapshot.content?.thinking_content || '';
                const charCount = thinkingContent.length;

                return (
                  <div key={index} className="snapshot-item expanded">
                    <div className="snapshot-header">
                      <div className="snapshot-title">
                        <span className="snapshot-number">📸 Snapshot #{index + 1}</span>
                        <span className="snapshot-time">{formatTimestamp(snapshot.timestamp)}</span>
                      </div>
                      <div className="snapshot-meta">
                        <span className="content-size">Content Size: {charCount.toLocaleString()} characters</span>
                      </div>
                    </div>
                    <div className="snapshot-content">
                      <div className="thinking-content-wrapper">
                        <pre className="thinking-content">{thinkingContent || 'No thinking content available'}</pre>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {showSessionDetails && downloadUrls && (
          <div className="session-details-panel">
            <h3>Session Download Links</h3>
            <div className="download-links">
              {Object.entries(downloadUrls.files || {}).map(([fileType, urlInfo]) => (
                <div key={fileType} className="download-link-item">
                  <strong>{fileType.replace('_', ' ').toUpperCase()}:</strong>
                  {urlInfo.presigned_url && (
                    <a href={urlInfo.presigned_url} target="_blank" rel="noopener noreferrer">
                      Download ({urlInfo.size || 'Unknown size'})
                    </a>
                  )}
                </div>
              ))}
              {downloadUrls.expires_in && (
                <p className="expiry-notice">Links expire in {downloadUrls.expires_in} minutes</p>
              )}
            </div>
          </div>
        )}

        <div className="chat-container" ref={chatContainerRef}>
          {status && (
            <div className={`status-indicator ${status}`}>
              Status: {status}
              {status === 'queued' && ' - Waiting in queue...'}
              {status === 'running' && ' - Processing...'}
            </div>
          )}

          <div className="message-list">
            {messages.map((message, index) => (
              <div key={index} className={`message ${message.role}`}>
                <div className="message-avatar">
                  {message.role === 'user' ? 'U' : 'A'}
                </div>
                <div className="message-content">
                  {message.isComplete && isTaskComplete ? (
                    <div className="complete-response">
                      <div className="final-report">
                        <ReactMarkdown
                          components={{
                            code({node, inline, className, children, ...props}) {
                              const match = /language-(\w+)/.exec(className || '');
                              return !inline && match ? (
                                <SyntaxHighlighter
                                  style={vscDarkPlus}
                                  language={match[1]}
                                  PreTag="div"
                                  {...props}
                                >
                                  {String(children).replace(/\n$/, '')}
                                </SyntaxHighlighter>
                              ) : (
                                <code className={className} {...props}>
                                  {children}
                                </code>
                              );
                            }
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      </div>

                      {snapshots.length > 0 && (
                        <div className="thinking-process-container">
                          <button
                            className="thinking-toggle-btn"
                            onClick={() => setShowThinkingProcess(!showThinkingProcess)}
                          >
                            {showThinkingProcess ? <FiChevronUp size={16} /> : <FiChevronDown size={16} />}
                            <span>Thinking Process ({snapshots.length} snapshots)</span>
                          </button>

                          {showThinkingProcess && (
                            <div className="thinking-process-content">
                              {snapshots.map((snapshot, idx) => (
                                <div key={idx} className="thinking-snapshot">
                                  <div className="thinking-snapshot-header">
                                    <span>Snapshot #{idx + 1}</span>
                                    <span className="thinking-time">{formatTimestamp(snapshot.timestamp)}</span>
                                  </div>
                                  <pre className="thinking-text">
                                    {snapshot.content?.thinking_content || 'No content'}
                                  </pre>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <ReactMarkdown
                      components={{
                        code({node, inline, className, children, ...props}) {
                          const match = /language-(\w+)/.exec(className || '');
                          return !inline && match ? (
                            <SyntaxHighlighter
                              style={vscDarkPlus}
                              language={match[1]}
                              PreTag="div"
                              {...props}
                            >
                              {String(children).replace(/\n$/, '')}
                            </SyntaxHighlighter>
                          ) : (
                            <code className={className} {...props}>
                              {children}
                            </code>
                          );
                        }
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  )}
                </div>
              </div>
            ))}

            {isLoading && messages[messages.length - 1]?.role === 'user' && (
              <div className="message assistant">
                <div className="message-avatar">A</div>
                <div className="message-content">
                  <div className="loading-dots">
                    <span className="loading-dot"></span>
                    <span className="loading-dot"></span>
                    <span className="loading-dot"></span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="input-container">
          {uploadedFiles.length > 0 && (
            <div className="file-upload-area">
              <div className="uploaded-files">
                {uploadedFiles.map((file, index) => (
                  <div key={index} className="uploaded-file">
                    <span>{file.name}</span>
                    <button className="remove-file-btn" onClick={() => removeFile(index)}>
                      <FiTrash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="input-wrapper">
            <textarea
              className="message-input"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              placeholder="Send a message..."
              rows={1}
            />
            <div className="input-controls">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                style={{ display: 'none' }}
                onChange={handleFileUpload}
              />
              <button
                className="input-btn"
                onClick={() => fileInputRef.current.click()}
              >
                <FiPaperclip size={20} />
              </button>

              {isLoading ? (
                <button className="input-btn" onClick={handleStopTask}>
                  <FiStopCircle size={20} />
                </button>
              ) : (
                <button
                  className="input-btn send-btn"
                  onClick={handleSendMessage}
                  disabled={!inputMessage.trim() && uploadedFiles.length === 0}
                >
                  <FiSend size={20} />
                </button>
              )}

              {currentSessionId && (
                <>
                  <button className="input-btn" onClick={handleShareSession} title="Share Session">
                    <FiShare2 size={20} />
                  </button>
                  <button className="input-btn" onClick={handleDownloadZip} title="Download ZIP">
                    <FiDownload size={20} />
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Query Sidebar */}
      {showQuerySidebar && (
        <div className="query-sidebar">
          <div className="query-sidebar-header">
            <h3>Query History</h3>
            <button
              className="toggle-sidebar-btn"
              onClick={() => setShowQuerySidebar(false)}
              title="Hide Query Sidebar"
            >
              ×
            </button>
          </div>
          <div className="query-sidebar-content">
            {allQueries.length === 0 ? (
              <div className="no-queries">No queries yet</div>
            ) : (
              <div className="query-list">
                {allQueries.map((item, index) => (
                  <div
                    key={index}
                    className={`query-item ${item.sessionId === currentSessionId ? 'active' : ''}`}
                    onClick={() => selectSession(item.sessionId)}
                  >
                    {item.totalTurns > 1 && (
                      <div className="multi-turn-badge">
                        Turn {item.turn}/{item.totalTurns}
                      </div>
                    )}
                    <div className="query-text">
                      {item.query}
                    </div>
                    {item.timestamp && (
                      <div className="query-timestamp">
                        {formatTimestamp(item.timestamp)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Toggle button when sidebar is hidden */}
      {!showQuerySidebar && (
        <button
          className="show-query-sidebar-btn"
          onClick={() => setShowQuerySidebar(true)}
          title="Show Query Sidebar"
        >
          <FiChevronDown size={20} />
        </button>
      )}

      {contextMenu && (
        <div
          className="context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <div
            className="context-menu-item delete"
            onClick={(e) => {
              handleDeleteSession(contextMenu.sessionId, e);
              closeContextMenu();
            }}
          >
            Hard Delete
          </div>
        </div>
      )}
    </div>
  );
}

export default App;