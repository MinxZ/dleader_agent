import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import { FiPlus, FiSend, FiPaperclip, FiTrash2, FiStopCircle, FiShare2, FiMoreVertical } from 'react-icons/fi';
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
  const [userId] = useState(`user_${uuidv4()}`);

  const chatContainerRef = useRef(null);
  const fileInputRef = useRef(null);
  const statusCheckInterval = useRef(null);
  const apiClient = useRef(new ApiClient(process.env.REACT_APP_API_URL || 'http://52.192.211.135:8001'));

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages]);

  const loadSessions = async () => {
    const allSessions = await apiClient.current.getAllSessions(userId);
    setSessions(allSessions.reverse());
  };

  const createNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setStatus(null);
    setUploadedFiles([]);
  };

  const selectSession = async (sessionId) => {
    setCurrentSessionId(sessionId);
    const history = await apiClient.current.getSessionHistory(sessionId, userId);
    if (history && history.turns) {
      const formattedMessages = [];
      history.turns.forEach(turn => {
        formattedMessages.push({
          role: 'user',
          content: turn.message
        });
        if (turn.response) {
          formattedMessages.push({
            role: 'assistant',
            content: turn.response
          });
        }
      });
      setMessages(formattedMessages);
    }
  };

  const handleFileUpload = (e) => {
    const files = Array.from(e.target.files);
    setUploadedFiles([...uploadedFiles, ...files]);
  };

  const removeFile = (index) => {
    setUploadedFiles(uploadedFiles.filter((_, i) => i !== index));
  };

  const checkStatus = useCallback(async (sessionId) => {
    const statusData = await apiClient.current.getStatus(sessionId, userId);

    if (statusData) {
      setStatus(statusData.status);

      if (statusData.status === 'completed' && statusData.response) {
        setMessages(prev => {
          const newMessages = [...prev];
          if (newMessages[newMessages.length - 1]?.role !== 'assistant') {
            newMessages.push({
              role: 'assistant',
              content: statusData.response
            });
          }
          return newMessages;
        });
        setIsLoading(false);
        clearInterval(statusCheckInterval.current);
        loadSessions();
      } else if (statusData.status === 'failed') {
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
  }, [userId]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() && uploadedFiles.length === 0) return;

    const userMessage = inputMessage.trim();
    setInputMessage('');
    setMessages([...messages, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    let sessionId;
    if (currentSessionId && messages.length > 0) {
      const result = await apiClient.current.continueSession(
        currentSessionId,
        userMessage,
        'en',
        userId,
        uploadedFiles
      );
      if (result) {
        sessionId = currentSessionId;
      }
    } else {
      sessionId = await apiClient.current.submitRequest(
        userMessage,
        'en',
        userId,
        uploadedFiles
      );
      if (sessionId) {
        setCurrentSessionId(sessionId);
      }
    }

    setUploadedFiles([]);

    if (sessionId) {
      statusCheckInterval.current = setInterval(() => {
        checkStatus(sessionId);
      }, 2000);
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
    document.addEventListener('click', closeContextMenu);
    return () => document.removeEventListener('click', closeContextMenu);
  }, []);

  return (
    <div className="app">
      <div className="sidebar">
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={createNewChat}>
            <FiPlus size={18} />
            New Chat
          </button>
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
                <button className="input-btn" onClick={handleShareSession}>
                  <FiShare2 size={20} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

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