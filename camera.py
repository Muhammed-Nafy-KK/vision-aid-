from blind_assist.camera import CameraStream


def main() -> None:
    camera = CameraStream()
    camera.start()
    try:
        frame = camera.get_frame(timeout=5.0)
        if frame is None:
            print("No camera frame received.")
        else:
            print(f"Camera ready. Frame size: {frame.shape[1]}x{frame.shape[0]}")
    finally:
        camera.stop()


if __name__ == "__main__":
    main()
