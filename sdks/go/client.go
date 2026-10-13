// AI Empire Go SDK
// Official Go client for the AI Empire API
package empire

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// EmpireError represents an API error
type EmpireError struct {
	StatusCode int
	Message    string
}

func (e *EmpireError) Error() string {
	return fmt.Sprintf("empire error %d: %s", e.StatusCode, e.Message)
}

// Client is the main Empire API client
type Client struct {
	BaseURL string
	Token   string
	HTTP    *http.Client
}

// NewClient creates a new Empire client
func NewClient(baseURL, token string) *Client {
	if baseURL == "" {
		baseURL = os.Getenv("EMPIRE_BASE_URL")
	}
	if baseURL == "" {
		baseURL = "http://localhost:8080"
	}
	if token == "" {
		token = os.Getenv("EMPIRE_TOKEN")
	}
	return &Client{
		BaseURL: baseURL,
		Token:   token,
		HTTP:    &http.Client{Timeout: 60 * time.Second},
	}
}

// Login authenticates with email + password, stores token
func (c *Client) Login(ctx context.Context, email, password string) error {
	body := map[string]string{"email": email, "password": password}
	var resp struct{ AccessToken string `json:"access_token"` }
	if err := c.do(ctx, "POST", "/api/auth/login", body, &resp); err != nil {
		return err
	}
	c.Token = resp.AccessToken
	return nil
}

// Health returns the server health
func (c *Client) Health(ctx context.Context) (map[string]any, error) {
	var resp map[string]any
	err := c.do(ctx, "GET", "/health", nil, &resp)
	return resp, err
}

// Capabilities returns the installed skills and tools
func (c *Client) Capabilities(ctx context.Context) (map[string]any, error) {
	var resp map[string]any
	err := c.do(ctx, "GET", "/api/capabilities", nil, &resp)
	return resp, err
}

// Chat sends a message
func (c *Client) Chat(ctx context.Context, message string, sessionID string) (map[string]any, error) {
	body := map[string]any{"message": message, "session_id": sessionID}
	var resp map[string]any
	err := c.do(ctx, "POST", "/api/chat", body, &resp)
	return resp, err
}

// CallTool invokes a tool
func (c *Client) CallTool(ctx context.Context, name string, args map[string]any) (any, error) {
	body := map[string]any{"name": name, "arguments": args}
	var resp any
	err := c.do(ctx, "POST", "/api/tools/call", body, &resp)
	return resp, err
}

func (c *Client) do(ctx context.Context, method, path string, body any, out any) error {
	var reqBody io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		reqBody = bytes.NewReader(b)
	}
	req, _ := http.NewRequestWithContext(ctx, method, c.BaseURL+path, reqBody)
	req.Header.Set("Content-Type", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	r, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer r.Body.Close()
	if r.StatusCode >= 400 {
		return &EmpireError{StatusCode: r.StatusCode, Message: r.Status}
	}
	if out != nil {
		return json.NewDecoder(r.Body).Decode(out)
	}
	return nil
}
