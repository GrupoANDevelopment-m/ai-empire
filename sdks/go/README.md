# AI Empire Go SDK

Official Go client for the AI Empire API.

## Installation
```bash
go get github.com/GrupoANDevelopment-m/ai-empire-go
```

## Usage
```go
package main

import (
    "context"
    "fmt"
    empire "github.com/GrupoANDevelopment-m/ai-empire-go"
)

func main() {
    c := empire.NewClient("https://empire.example.com", "")
    c.Login(context.Background(), "user@example.com", "password")
    
    resp, _ := c.Chat(context.Background(), "Hello!", "")
    fmt.Println(resp)
}
```
