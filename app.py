from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime
import json
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for React Native requests

# Store completed steps in memory (you can replace with database)
navigation_sessions = {}
completed_steps = []
location_history = {}  # New: Store location tracking history

# Single destination configuration - modify this as needed
CURRENT_DESTINATION = {
    "id": "dest_active",
    "name": "Sundernagar Bus Stand",
    "description": "Main Bus Stand - Public Transport Hub",
    "category": "Transport",
    "coordinates": {
        "latitude": 31.53710695981553,
        "longitude": 76.89220591261135
    },
    "address": "Bus Stand Road, Sundernagar, Mandi, Himachal Pradesh",
    "distance": "2.5 km",
    "estimated_time": "18 min",
    "priority": "high",
    "instructions": "Navigate to main bus stand for public transport"
}


@app.route('/api/destination', methods=['GET'])
def get_current_destination():
    """
    Get the current active destination for blind navigation
    Query params:
    - user_location: "lat,lng" for distance calculation (required)
    """
    try:
        user_location = request.args.get('user_location')
        
        if not user_location:
            return jsonify({
                "success": False,
                "error": "user_location parameter required (format: lat,lng)"
            }), 400
        
        destination = CURRENT_DESTINATION.copy()
        
        # Calculate real-time distance if user location provided
        try:
            lat, lng = map(float, user_location.split(','))
            dest_lat = destination['coordinates']['latitude']
            dest_lng = destination['coordinates']['longitude']
            
            # Haversine distance calculation
            import math
            R = 6371  # Earth's radius in km
            dlat = math.radians(dest_lat - lat)
            dlng = math.radians(dest_lng - lng)
            a = (math.sin(dlat/2)**2 + 
                 math.cos(math.radians(lat)) * math.cos(math.radians(dest_lat)) * 
                 math.sin(dlng/2)**2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = R * c
            
            destination['calculated_distance'] = f"{distance:.1f} km"
            destination['calculated_time'] = f"{max(5, int(distance * 3))} min"  # Walking estimate
            destination['distance_meters'] = int(distance * 1000)
            
        except Exception as calc_error:
            print(f"Distance calculation error: {calc_error}")
            # Keep original values if calculation fails
        
        print(f"📍 Destination requested for blind navigation: {destination['name']}")
        print(f"🎯 Distance: {destination.get('calculated_distance', destination['distance'])}")
        
        return jsonify({
            "success": True,
            "destination": destination,
            "auto_start": True,  # Signal that navigation should start automatically
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching destination: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/location/update', methods=['POST'])
def update_location():
    """
    Receive continuous location updates from the app
    Expected data: {
        "session_id": "optional_session_id", 
        "user_id": "optional_user_id",
        "location": {
            "latitude": float,
            "longitude": float,
            "altitude": float (optional),
            "accuracy": float (optional),
            "speed": float (optional),
            "heading": float (optional)
        },
        "timestamp": "ISO_timestamp"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        location_data = data.get('location')
        if not location_data or 'latitude' not in location_data or 'longitude' not in location_data:
            return jsonify({
                "success": False,
                "error": "Location data with latitude and longitude required"
            }), 400
        
        # Create location record
        location_record = {
            "session_id": data.get('session_id', 'anonymous'),
            "user_id": data.get('user_id', 'anonymous'),
            "location": location_data,
            "timestamp": data.get('timestamp', datetime.datetime.now().isoformat()),
            "server_received_at": datetime.datetime.now().isoformat()
        }
        
        # Store in location history
        session_key = data.get('session_id', 'anonymous')
        if session_key not in location_history:
            location_history[session_key] = []
        
        location_history[session_key].append(location_record)
        
        # Keep only last 100 locations per session to prevent memory issues
        if len(location_history[session_key]) > 100:
            location_history[session_key] = location_history[session_key][-100:]
        
        # Calculate distance to destination if available
        distance_to_destination = None
        if CURRENT_DESTINATION:
            try:
                import math
                R = 6371  # Earth's radius in km
                lat1 = math.radians(location_data['latitude'])
                lng1 = math.radians(location_data['longitude'])
                lat2 = math.radians(CURRENT_DESTINATION['coordinates']['latitude'])
                lng2 = math.radians(CURRENT_DESTINATION['coordinates']['longitude'])
                
                dlat = lat2 - lat1
                dlng = lng2 - lng1
                a = (math.sin(dlat/2)**2 + 
                     math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2)
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                distance_to_destination = R * c  # Distance in km
                
            except Exception as calc_error:
                print(f"Distance calculation error: {calc_error}")
        
        # Log location update (less verbose to avoid spam)
        print(f"📍 Location update: {location_data['latitude']:.6f}, {location_data['longitude']:.6f}")
        if distance_to_destination:
            print(f"🎯 Distance to destination: {distance_to_destination:.1f}km")
        
        response_data = {
            "success": True,
            "message": "Location updated successfully",
            "session_id": session_key,
            "received_at": location_record["server_received_at"]
        }
        
        # Add distance info if calculated
        if distance_to_destination is not None:
            response_data["distance_to_destination"] = {
                "kilometers": round(distance_to_destination, 3),
                "meters": round(distance_to_destination * 1000),
                "destination_name": CURRENT_DESTINATION['name']
            }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"❌ Error updating location: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/location/history/<session_id>', methods=['GET'])
def get_location_history(session_id):
    """Get location history for a specific session"""
    try:
        if session_id not in location_history:
            return jsonify({
                "success": False,
                "error": "No location history found for this session"
            }), 404
        
        history = location_history[session_id]
        
        # Calculate some basic stats
        if history:
            total_points = len(history)
            first_location = history[0]
            last_location = history[-1]
            
            # Calculate total distance traveled (approximate)
            total_distance = 0
            for i in range(1, len(history)):
                prev_loc = history[i-1]['location']
                curr_loc = history[i]['location']
                
                try:
                    import math
                    R = 6371
                    lat1, lng1 = math.radians(prev_loc['latitude']), math.radians(prev_loc['longitude'])
                    lat2, lng2 = math.radians(curr_loc['latitude']), math.radians(curr_loc['longitude'])
                    
                    dlat, dlng = lat2 - lat1, lng2 - lng1
                    a = (math.sin(dlat/2)**2 + 
                         math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2)
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                    total_distance += R * c
                except:
                    pass
        else:
            total_points = 0
            first_location = None
            last_location = None
            total_distance = 0
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "location_history": history,
            "stats": {
                "total_points": total_points,
                "total_distance_km": round(total_distance, 3),
                "first_location": first_location,
                "last_location": last_location,
                "time_span": {
                    "start": first_location['timestamp'] if first_location else None,
                    "end": last_location['timestamp'] if last_location else None
                }
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/location/current/<session_id>', methods=['GET'])
def get_current_location(session_id):
    """Get the most recent location for a session"""
    try:
        if session_id not in location_history or not location_history[session_id]:
            return jsonify({
                "success": False,
                "error": "No location data found for this session"
            }), 404
        
        latest_location = location_history[session_id][-1]
        
        # Calculate time since last update
        try:
            last_update = datetime.datetime.fromisoformat(latest_location['server_received_at'].replace('Z', '+00:00'))
            time_since_update = datetime.datetime.now() - last_update
            seconds_since_update = time_since_update.total_seconds()
        except:
            seconds_since_update = None
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "current_location": latest_location,
            "seconds_since_last_update": seconds_since_update,
            "is_recent": seconds_since_update < 30 if seconds_since_update else False  # Consider recent if < 30 seconds
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/destination/update', methods=['POST'])
def update_destination():
    """
    Update the current destination (admin endpoint)
    Expected data: {
        "name": "string",
        "coordinates": {"latitude": float, "longitude": float},
        "address": "string",
        "instructions": "string"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        # Update current destination
        global CURRENT_DESTINATION
        if 'name' in data:
            CURRENT_DESTINATION['name'] = data['name']
        if 'coordinates' in data:
            CURRENT_DESTINATION['coordinates'] = data['coordinates']
        if 'address' in data:
            CURRENT_DESTINATION['address'] = data['address']
        if 'instructions' in data:
            CURRENT_DESTINATION['instructions'] = data['instructions']
        
        CURRENT_DESTINATION['updated_at'] = datetime.datetime.now().isoformat()
        
        print(f"🔄 Destination updated: {CURRENT_DESTINATION['name']}")
        
        return jsonify({
            "success": True,
            "message": "Destination updated successfully",
            "destination": CURRENT_DESTINATION,
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error updating destination: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/start', methods=['POST'])
def start_navigation():
    """
    Start a new navigation session for blind navigation
    Expected data: {
        "session_id": "unique_session_id",
        "user_location": {"latitude": float, "longitude": float},
        "total_steps": int,
        "total_distance": "string",
        "total_duration": "string"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({
                "success": False,
                "error": "session_id is required"
            }), 400
        
        # Store navigation session
        navigation_sessions[session_id] = {
            "session_id": session_id,
            "destination": CURRENT_DESTINATION.copy(),
            "user_location": data.get('user_location'),
            "total_steps": data.get('total_steps'),
            "total_distance": data.get('total_distance'),
            "total_duration": data.get('total_duration'),
            "started_at": datetime.datetime.now().isoformat(),
            "completed_steps": 0,
            "status": "active",
            "user_type": "blind_navigation",
            "location_tracking_enabled": True  # Enable location tracking for this session
        }
        
        # Initialize location history for this session if not exists
        if session_id not in location_history:
            location_history[session_id] = []
        
        print(f"🚀 BLIND NAVIGATION STARTED")
        print(f"📋 Session: {session_id}")
        print(f"🎯 Destination: {CURRENT_DESTINATION['name']}")
        print(f"📍 From: {data.get('user_location')}")
        print(f"📊 Route: {data.get('total_steps')} steps, {data.get('total_distance')}, {data.get('total_duration')}")
        print(f"🔊 Voice navigation active")
        print(f"📍 Location tracking enabled")
        print("=" * 60)
        
        return jsonify({
            "success": True,
            "message": f"Navigation started to {CURRENT_DESTINATION['name']}",
            "session_id": session_id,
            "destination_name": CURRENT_DESTINATION['name'],
            "voice_announcement": f"Navigation started. Proceeding to {CURRENT_DESTINATION['name']}. {data.get('total_distance')} ahead.",
            "location_tracking_enabled": True,
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error starting blind navigation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/step-completed', methods=['POST'])
def step_completed():
    """
    Receive step completion notification for blind navigation
    Expected data: {
        "session_id": "unique_session_id",
        "step_index": int,
        "step_instruction": "string",
        "step_distance": "string",
        "current_location": {"latitude": float, "longitude": float},
        "accuracy": float
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        session_id = data.get('session_id')
        step_index = data.get('step_index')
        step_instruction = data.get('step_instruction')
        current_location = data.get('current_location')
        
        if not all([session_id, step_index is not None, step_instruction, current_location]):
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400
        
        # Check if session exists
        if session_id not in navigation_sessions:
            return jsonify({
                "success": False,
                "error": "Navigation session not found"
            }), 404
        
        # Create step completion record
        step_completion = {
            "session_id": session_id,
            "step_index": step_index,
            "step_instruction": step_instruction,
            "step_distance": data.get('step_distance', 'N/A'),
            "current_location": current_location,
            "completion_time": datetime.datetime.now().isoformat(),
            "accuracy": data.get('accuracy'),
            "user_type": "blind_navigation"
        }
        
        # Add to completed steps list
        completed_steps.append(step_completion)
        
        # Update session progress
        navigation_sessions[session_id]['completed_steps'] = step_index + 1
        navigation_sessions[session_id]['last_update'] = datetime.datetime.now().isoformat()
        
        destination_name = navigation_sessions[session_id]['destination']['name']
        
        # Log step completion for blind navigation
        print(f"✅ STEP {step_index + 1} COMPLETED - BLIND NAVIGATION")
        print(f"🎯 Destination: {destination_name}")
        print(f"📋 Session: {session_id}")
        print(f"🗣️  Instruction completed: {step_instruction}")
        print(f"📍 Current location: {current_location['latitude']:.6f}, {current_location['longitude']:.6f}")
        print(f"🎯 GPS accuracy: {data.get('accuracy', 'Unknown')}m")
        print(f"⏱️  Completed at: {step_completion['completion_time']}")
        print("=" * 60)
        
        # Calculate progress
        total_steps = navigation_sessions[session_id].get('total_steps', 1)
        progress_percentage = ((step_index + 1) / total_steps) * 100
        steps_remaining = total_steps - (step_index + 1)
        
        # Prepare voice announcement for next step
        if steps_remaining > 0:
            voice_announcement = f"Step completed. {steps_remaining} steps remaining to {destination_name}."
        else:
            voice_announcement = f"Final step completed. You have arrived at {destination_name}."
        
        return jsonify({
            "success": True,
            "message": f"Step {step_index + 1} completed",
            "step_index": step_index,
            "destination_name": destination_name,
            "progress": {
                "completed_steps": step_index + 1,
                "total_steps": total_steps,
                "percentage": round(progress_percentage, 1),
                "steps_remaining": steps_remaining
            },
            "voice_announcement": voice_announcement,
            "session_status": "active",
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error processing blind navigation step: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/complete', methods=['POST'])
def navigation_complete():
    """
    Mark blind navigation as completed
    Expected data: {
        "session_id": "unique_session_id",
        "final_location": {"latitude": float, "longitude": float},
        "total_time": "string",
        "total_distance_traveled": float
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        session_id = data.get('session_id')
        if not session_id or session_id not in navigation_sessions:
            return jsonify({
                "success": False,
                "error": "Invalid session"
            }), 404
        
        # Update session as completed
        navigation_sessions[session_id]['status'] = 'completed'
        navigation_sessions[session_id]['completed_at'] = datetime.datetime.now().isoformat()
        navigation_sessions[session_id]['final_location'] = data.get('final_location')
        navigation_sessions[session_id]['actual_total_time'] = data.get('total_time')
        navigation_sessions[session_id]['actual_distance_traveled'] = data.get('total_distance_traveled')
        navigation_sessions[session_id]['location_tracking_enabled'] = False  # Disable location tracking
        
        destination_name = navigation_sessions[session_id]['destination']['name']
        
        print(f"🎉 BLIND NAVIGATION COMPLETED!")
        print(f"🎯 Destination: {destination_name}")
        print(f"📋 Session: {session_id}")
        print(f"📍 Final location: {data.get('final_location')}")
        print(f"⏱️  Total time: {data.get('total_time', 'N/A')}")
        print(f"🛣️  Distance traveled: {data.get('total_distance_traveled', 'N/A')}km")
        print(f"🔊 Navigation completed successfully")
        print(f"📍 Location tracking stopped")
        print("=" * 60)
        
        return jsonify({
            "success": True,
            "message": f"Navigation to {destination_name} completed successfully",
            "destination_name": destination_name,
            "voice_announcement": f"Navigation complete. You have successfully arrived at {destination_name}.",
            "location_tracking_stopped": True,
            "session_summary": {
                "session_id": session_id,
                "destination": destination_name,
                "total_steps_completed": navigation_sessions[session_id]['completed_steps'],
                "actual_time": data.get('total_time'),
                "actual_distance": data.get('total_distance_traveled'),
                "completed_at": navigation_sessions[session_id]['completed_at']
            },
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error completing blind navigation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/status/<session_id>', methods=['GET'])
def get_navigation_status(session_id):
    """Get current blind navigation status and progress"""
    try:
        if session_id not in navigation_sessions:
            return jsonify({
                "success": False,
                "error": "Navigation session not found"
            }), 404
        
        session = navigation_sessions[session_id]
        session_steps = [step for step in completed_steps if step['session_id'] == session_id]
        
        # Get location tracking info
        location_tracking_info = {
            "enabled": session.get('location_tracking_enabled', False),
            "total_location_points": len(location_history.get(session_id, [])),
            "latest_location": location_history[session_id][-1] if session_id in location_history and location_history[session_id] else None
        }
        
        return jsonify({
            "success": True,
            "session": session,
            "completed_steps_detail": session_steps,
            "location_tracking": location_tracking_info,
            "summary": {
                "total_steps": session.get('total_steps', 0),
                "completed_steps": len(session_steps),
                "progress_percentage": (len(session_steps) / session.get('total_steps', 1)) * 100 if session.get('total_steps') else 0,
                "status": session.get('status', 'unknown'),
                "destination": session['destination']['name']
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/sessions', methods=['GET'])
def get_all_sessions():
    """Get all blind navigation sessions"""
    try:
        return jsonify({
            "success": True,
            "sessions": list(navigation_sessions.values()),
            "total_sessions": len(navigation_sessions),
            "total_completed_steps": len(completed_steps),
            "total_location_points": sum(len(history) for history in location_history.values()),
            "active_location_tracking_sessions": len([s for s in navigation_sessions.values() if s.get('location_tracking_enabled', False)]),
            "current_destination": CURRENT_DESTINATION['name']
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "success": True,
        "message": "Blind Navigation API is running!",
        "timestamp": datetime.datetime.now().isoformat(),
        "active_sessions": len([s for s in navigation_sessions.values() if s.get('status') == 'active']),
        "total_sessions": len(navigation_sessions),
        "location_tracking_sessions": len([s for s in navigation_sessions.values() if s.get('location_tracking_enabled', False)]),
        "total_location_points": sum(len(history) for history in location_history.values()),
        "current_destination": CURRENT_DESTINATION['name'],
        "service_type": "blind_navigation"
    }), 200
    


@app.route('/api/user_current_location', methods=['GET'])  # 'methods' not 'method'
def user_current_location():  
    return jsonify({ 
        "success": True,
        "longitude": "31.51645",
        "latitude": "76.87841"
    }), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
    
if __name__ == '__main__':
    print("🚀 Starting Blind Navigation API Server...")
    print("🔊 Optimized for blind users - voice navigation")
    print(f"🎯 Current destination: {CURRENT_DESTINATION['name']}")
    print("📡 Listening for navigation requests...")
    print("📍 Location tracking enabled")
    print("🔗 API Endpoints:")
    print("   GET /api/destination - Get current destination")
    print("   POST /api/destination/update - Update destination (admin)")
    print("   POST /api/location/update - Receive location updates")
    print("   GET /api/location/history/<session_id> - Get location history")
    print("   GET /api/location/current/<session_id> - Get current location")
    print("   POST /api/navigation/start - Start navigation session")
    print("   POST /api/navigation/step-completed - Step completion notification")
    print("   POST /api/navigation/complete - Mark navigation complete")
    print("   GET /api/navigation/status/<session_id> - Get session status")
    print("   GET /api/navigation/sessions - Get all sessions")
    print("   GET /api/health - Health check")
    print("=" * 60)
    port = int(os.environ.get('PORT', 5000))
    # Run the server
    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=port,       # Port 5000
        debug=False       # Enable debug mode
    )

