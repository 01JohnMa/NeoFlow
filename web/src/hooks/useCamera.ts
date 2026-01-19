import { useState, useCallback, useRef, useEffect } from 'react'

export interface UseCameraOptions {
  facingMode?: 'user' | 'environment'
  width?: number
  height?: number
}

export function useCamera(options: UseCameraOptions = {}) {
  const { facingMode = 'environment', width = 1920, height = 1080 } = options

  const [isOpen, setIsOpen] = useState(false)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [currentFacingMode, setCurrentFacingMode] = useState<'user' | 'environment'>(facingMode)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  // 当 stream 更新时，自动绑定到 video 元素
  useEffect(() => {
    if (stream && videoRef.current) {
      videoRef.current.srcObject = stream
      // 确保视频播放
      videoRef.current.play().catch((err) => {
        console.error('Video play error:', err)
      })
    }
  }, [stream])

  // 监听 videoRef 变化，确保 stream 绑定
  const setVideoRef = useCallback((element: HTMLVideoElement | null) => {
    videoRef.current = element
    if (element && stream) {
      element.srcObject = stream
      element.play().catch((err) => {
        console.error('Video play error:', err)
      })
    }
  }, [stream])

  // Open camera
  const openCamera = useCallback(async () => {
    try {
      setError(null)

      // 检查是否在安全上下文中（HTTPS 或 localhost）
      if (!window.isSecureContext) {
        throw new Error('相机功能需要 HTTPS 连接。请使用 HTTPS 或 localhost 访问。')
      }

      const constraints: MediaStreamConstraints = {
        video: {
          facingMode: currentFacingMode,
          width: { ideal: width },
          height: { ideal: height },
        },
        audio: false,
      }

      const mediaStream = await navigator.mediaDevices.getUserMedia(constraints)
      setStream(mediaStream)
      setIsOpen(true)

      return mediaStream
    } catch (err) {
      let errorMessage = '无法访问摄像头'
      if (err instanceof Error) {
        if (err.name === 'NotAllowedError') {
          errorMessage = '相机权限被拒绝，请在浏览器设置中允许访问相机'
        } else if (err.name === 'NotFoundError') {
          errorMessage = '未找到可用的摄像头设备'
        } else if (err.name === 'NotReadableError') {
          errorMessage = '摄像头被其他应用占用'
        } else {
          errorMessage = err.message
        }
      }
      setError(errorMessage)
      throw new Error(errorMessage)
    }
  }, [currentFacingMode, width, height])

  // Close camera
  const closeCamera = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop())
      setStream(null)
    }
    setIsOpen(false)
    setError(null)
  }, [stream])

  // Capture photo
  const capturePhoto = useCallback((): File | null => {
    if (!videoRef.current || !stream) {
      setError('摄像头未就绪')
      return null
    }

    const video = videoRef.current
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight

    const ctx = canvas.getContext('2d')
    if (!ctx) {
      setError('无法创建画布上下文')
      return null
    }

    ctx.drawImage(video, 0, 0)

    // Convert to blob and then to File
    const dataUrl = canvas.toDataURL('image/jpeg', 0.9)
    const byteString = atob(dataUrl.split(',')[1])
    const mimeString = dataUrl.split(',')[0].split(':')[1].split(';')[0]
    const ab = new ArrayBuffer(byteString.length)
    const ia = new Uint8Array(ab)

    for (let i = 0; i < byteString.length; i++) {
      ia[i] = byteString.charCodeAt(i)
    }

    const blob = new Blob([ab], { type: mimeString })
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
    const file = new File([blob], `photo-${timestamp}.jpg`, { type: 'image/jpeg' })

    return file
  }, [stream])

  // Switch camera (front/back)
  const switchCamera = useCallback(async () => {
    // 先停止当前流
    if (stream) {
      stream.getTracks().forEach((track) => track.stop())
    }
    
    const newFacingMode = currentFacingMode === 'user' ? 'environment' : 'user'
    setCurrentFacingMode(newFacingMode)
    
    try {
      const constraints: MediaStreamConstraints = {
        video: {
          facingMode: newFacingMode,
          width: { ideal: width },
          height: { ideal: height },
        },
        audio: false,
      }

      const mediaStream = await navigator.mediaDevices.getUserMedia(constraints)
      setStream(mediaStream)
      setIsOpen(true)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '无法切换摄像头'
      setError(errorMessage)
    }
  }, [stream, currentFacingMode, width, height])

  // Check if camera is supported
  const isSupported = typeof navigator !== 'undefined' && 
    'mediaDevices' in navigator && 
    'getUserMedia' in navigator.mediaDevices

  return {
    isOpen,
    isSupported,
    stream,
    error,
    videoRef,
    setVideoRef,
    openCamera,
    closeCamera,
    capturePhoto,
    switchCamera,
  }
}

