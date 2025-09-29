import axios from 'axios';

class ApiClient {
  constructor(baseUrl = process.env.REACT_APP_API_URL || 'http://52.192.211.135:8001') {
    this.baseUrl = baseUrl;
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 30000,
    });
  }

  async healthCheck() {
    try {
      const response = await this.client.get('/health');
      return response.status === 200;
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  }

  async submitRequest(message, language = 'en', userId = null, files = null) {
    try {
      const formData = new FormData();
      formData.append('message', message);
      formData.append('language', language);
      formData.append('user_id', userId);

      if (files && files.length > 0) {
        files.forEach(file => {
          formData.append('files', file);
        });
      }

      const response = await this.client.post('/chat-queue', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.status === 200) {
        return response.data.session_id;
      }
      return null;
    } catch (error) {
      console.error('Error submitting request:', error);
      return null;
    }
  }

  async continueSession(sessionId, message, language = 'en', userId = null, files = null) {
    try {
      const formData = new FormData();
      formData.append('message', message);
      formData.append('language', language);
      formData.append('user_id', userId);

      if (files && files.length > 0) {
        files.forEach(file => {
          formData.append('files', file);
        });
      }

      formData.append('session_id', sessionId);
      const response = await this.client.post('/continue-session', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.status === 200) {
        return response.data;
      }
      return null;
    } catch (error) {
      console.error('Error continuing session:', error);
      return null;
    }
  }

  async getStatus(sessionId, userId) {
    try {
      const response = await this.client.get(`/status/${sessionId}`, {
        params: { user_id: userId },
      });
      if (response.status === 200) {
        return response.data;
      }
      return null;
    } catch (error) {
      console.error('Error getting status:', error);
      return null;
    }
  }

  async stopTask(sessionId, userId) {
    try {
      const response = await this.client.post(`/stop/${sessionId}`, null, {
        params: { user_id: userId },
      });
      return response.status === 200;
    } catch (error) {
      console.error('Error stopping task:', error);
      return false;
    }
  }

  async getAllSessions(userId = null) {
    try {
      const params = userId ? { user_id: userId } : {};
      const response = await this.client.get('/all-sessions', { params });
      if (response.status === 200) {
        return response.data.sessions || [];
      }
      return [];
    } catch (error) {
      console.error('Error getting all sessions:', error);
      return [];
    }
  }

  async getSessionHistory(sessionId, userId) {
    try {
      // Use the multiturn-session endpoint to get session details
      const response = await this.client.get(`/multiturn-session/${sessionId}`, {
        params: { user_id: userId },
      });
      if (response.status === 200) {
        return response.data;
      }
      return null;
    } catch (error) {
      console.error('Error getting session history:', error);
      return null;
    }
  }

  async getDownloadUrl(sessionId, userId) {
    try {
      const response = await this.client.get(`/download-urls/${sessionId}`, {
        params: { user_id: userId },
      });
      if (response.status === 200) {
        const files = response.data.files || {};
        if (files.session_zip && files.session_zip.presigned_url) {
          return files.session_zip.presigned_url;
        }
      }
    } catch (error) {
      console.error('Error getting download URL:', error);
    }

    return `${this.baseUrl}/download/${sessionId}?user_id=${userId}`;
  }

  async deleteSession(sessionId, userId) {
    try {
      // Use the hard-delete endpoint
      const response = await this.client.delete(`/hard-delete/${sessionId}`, {
        params: { user_id: userId },
      });
      return response.status === 200;
    } catch (error) {
      console.error('Error deleting session:', error);
      return false;
    }
  }

  async getSnapshots(sessionId, userId) {
    try {
      const response = await this.client.get(`/snapshots/${sessionId}`, {
        params: { user_id: userId },
      });
      if (response.status === 200) {
        return response.data;
      }
      return null;
    } catch (error) {
      console.error('Error getting snapshots:', error);
      return null;
    }
  }

  async getDownloadUrls(sessionId, userId) {
    try {
      const response = await this.client.get(`/download-urls/${sessionId}`, {
        params: { user_id: userId },
      });
      if (response.status === 200) {
        return response.data;
      }
      return null;
    } catch (error) {
      console.error('Error getting download URLs:', error);
      return null;
    }
  }

  async getMultiturnSession(sessionId, userId) {
    try {
      const response = await this.client.get(`/multiturn-session/${sessionId}`, {
        params: { user_id: userId },
      });
      if (response.status === 200) {
        return response.data;
      }
      return null;
    } catch (error) {
      console.error('Error getting multi-turn session:', error);
      return null;
    }
  }

  async getResults(sessionId, userId) {
    try {
      const response = await this.client.get(`/results/${sessionId}`, {
        params: { user_id: userId },
      });
      if (response.status === 200) {
        return response.data;
      }
      return null;
    } catch (error) {
      console.error('Error getting results:', error);
      return null;
    }
  }
}

export default ApiClient;