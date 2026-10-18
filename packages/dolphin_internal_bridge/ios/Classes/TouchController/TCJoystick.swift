// Copyright 2022 DolphiniOS Project
// SPDX-License-Identifier: GPL-2.0-or-later

import Foundation
import UIKit

class TCJoystick: UIView
{
  @IBInspectable var joystickType: Int = 10 // default: GC stick
  var port: Int = 0
  
  override init(frame: CGRect)
  {
    super.init(frame: frame)
  }
  
  required init?(coder: NSCoder)
  {
    super.init(coder: coder)
  }
  
  override func awakeFromNib()
  {
    super.awakeFromNib()
    sharedInit()
  }
  
  func sharedInit()
  {
    // Create the range
    let rangeImage = createImageView(imageName: "gcwii_joystick_range")
    self.addSubview(rangeImage)
    
    // Create handle
    let handleView = createImageView(imageName: TCButtonType(rawValue: joystickType)!.getImageName())
    let panHandler = UIPanGestureRecognizer(target: self, action: #selector(handlePan))
    handleView.isUserInteractionEnabled = true
    handleView.addGestureRecognizer(panHandler)
    self.addSubview(handleView)
    
    // Set background color to transparent
    self.backgroundColor = UIColor.clear
  }
  
  func createImageView(imageName: String) -> UIImageView
  {
    // In Interface Builder, the default bundle is not Dolphin's, so we must specify
    // the bundle for the image to load correctly
    let image = UIImage(named: imageName, in: Bundle(for: type(of: self)), compatibleWith: nil)
    
    // Create the view
    let imageView = UIImageView(frame: CGRect(x: 0, y: 0, width: self.frame.width - (self.frame.width / 3), height: self.frame.height - (self.frame.height / 3)))
    imageView.image = image
    imageView.center = self.convert(self.center, from: self.superview)
    
    return imageView
  }
  
  @objc func handlePan(gesture: UIPanGestureRecognizer)
  {
    var point: CGPoint
    var joyAxises: [CGFloat] = [ 0, 0, 0, 0 ]
    
    if (gesture.state == .ended || gesture.state == .cancelled || gesture.state == .failed)
    {
      // Reset to center
      point = boundsCenter
    }
    else
    {
      // Get points
      point = gesture.location(in: self)
      let joystickCenter = boundsCenter
      
      // Calculate differences
      let xDiff = point.x - joystickCenter.x
      let yDiff = point.y - joystickCenter.y
      
      // Calculate distance
      var distance = sqrt(pow(xDiff, 2) + pow(yDiff, 2))
      let maxDistance = self.bounds.width / 3

      if (distance > maxDistance)
      {
        // Calculate maximum points
        let xMax = joystickCenter.x + maxDistance * (xDiff / distance)
        let yMax = joystickCenter.y + maxDistance * (yDiff / distance)

        point = CGPoint(x: xMax, y: yMax)
      }

      // Calculate axis values for ButtonManager
      // Based on Android's getAxisValues()
      let axises = (y: yDiff / maxDistance, x: xDiff / maxDistance)
      joyAxises = [max(-1, min(axises.y, 0)), max(0, min(axises.y, 1)), max(-1, min(axises.x, 0)), max(0, min(axises.x, 1))]
    }
    
    // Send axises values
    let axisStartIdx = joystickType
    for (i, axis) in joyAxises.enumerated()
    {
      TCManagerInterface.setAxisValueFor(axisStartIdx + i + 1, controller: port, value: Float(axis))
    }
    
    gesture.view?.center = point
  }

  // NeoStation Build 484: the touch-layout editor may move and scale the
  // joystick with a transform. The original frame/superview-centre maths
  // included that transform; the centre and travel are measured in the
  // joystick's own (untransformed) coordinates instead, which is identical
  // without a transform.
  private var boundsCenter: CGPoint
  {
    return CGPoint(x: bounds.midX, y: bounds.midY)
  }

  /// Releases the stick: neutral axes and the handle back in the centre.
  @objc func resetToCenter()
  {
    for recognizer in subviews.flatMap({ $0.gestureRecognizers ?? [] }) where recognizer.isEnabled
    {
      // Ends a drag in progress so its next movement cannot press again.
      recognizer.isEnabled = false
      recognizer.isEnabled = true
    }
    for i in 0..<4
    {
      TCManagerInterface.setAxisValueFor(joystickType + i + 1, controller: port, value: 0)
    }
    subviews.last?.center = boundsCenter
  }

}

