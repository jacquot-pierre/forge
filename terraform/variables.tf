variable "virtual_environment_api_token" {
  description = "Token to connect Proxmox API"
  type = string
}

variable "virtual_environment_endpoint" {
  description = "Adress or IP to proxmox"
  type = string
  default = "http://192.168.1.70:8006"
}

variable "virtual_environment_insecure" {
  description = "TLS or no TLS"
  type = bool
  default = true
}

variable "virtual_environment_ssh_username" {
  description = "User use to ssh to the proxmox server"
  type = string
  default = "root"
}