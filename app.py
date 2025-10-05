from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime
import json
import os

app = Flask(__name__)
CORS(app)

navigation_sessions = {}
completed_steps = []
active_steps = []  # NEW: Track active steps
location_history = {}

CURRENT_DESTINATION = {
    "id": "dest_active",
    "name": "Kangra Bus Stand",
    "description": "Main Bus Stand - Public Transport Hub",
    "category": "Transport",
    "coordinates": {
        "latitude": 32.09920,
        "longitude": 76.26910
    },
    "address": "Bus Stand Road, Kangra, Himachal Pradesh",
    "distance": "TBD",
    "estimated_time": "TBD",
    "priority": "high",
    "instructions": "Navigate to Kangra bus stand for public transport"
}


@app.route('/api/destination', methods=['GET'])
def get_current_destination():
    """Get the current active destination for blind navigation"""
    try:
        user_location = request.args.get('user_location')
        
        if not user_location:
            return jsonify({
                "success": False,
                "error": "user_location parameter required (format: lat,lng)"
            }), 400
        
        destination = CURRENT_DESTINATION.copy()
        
        try:
            lat, lng = map(float, user_location.split(','))
            dest_lat = destination['coordinates']['latitude']
            dest_lng = destination['coordinates']['longitude']
            
            import math
            R = 6371
            dlat = math.radians(dest_lat - lat)
            dlng = math.radians(dest_lng - lng)
            a = (math.sin(dlat/2)**2 + 
                 math.cos(math.radians(lat)) * math.cos(math.radians(dest_lat)) * 
                 math.sin(dlng/2)**2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = R * c
            
            destination['calculated_distance'] = f"{distance:.1f} km"
            destination['calculated_time'] = f"{max(5, int(distance * 3))} min"
            destination['distance_meters'] = int(distance * 1000)
            
        except Exception as calc_error:
            print(f"Distance calculation error: {calc_error}")
        
        print(f"📍 Destination requested: {destination['name']}")
        print(f"🎯 Distance: {destination.get('calculated_distance', destination['distance'])}")
        
        return jsonify({
            "success": True,
            "destination": destination,
            "auto_start": True,
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching destination: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/location/simple', methods=['POST'])
def simple_location_update():
    """
    Simple endpoint to receive just latitude, longitude, and session_id
    Expected data: {
        "session_id": "string",
        "latitude": float,
        "longitude": float
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
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if not all([session_id, latitude is not None, longitude is not None]):
            return jsonify({
                "success": False,
                "error": "session_id, latitude, and longitude are required"
            }), 400
        
        location_record = {
            "session_id": session_id,
            "location": {
                "latitude": float(latitude),
                "longitude": float(longitude)
            },
            "timestamp": datetime.datetime.now().isoformat(),
            "server_received_at": datetime.datetime.now().isoformat()
        }
        
        if session_id not in location_history:
            location_history[session_id] = []
        
        location_history[session_id].append(location_record)
        
        if len(location_history[session_id]) > 100:
            location_history[session_id] = location_history[session_id][-100:]
        
        distance_to_destination = None
        if CURRENT_DESTINATION:
            try:
                import math
                R = 6371
                lat1 = math.radians(latitude)
                lng1 = math.radians(longitude)
                lat2 = math.radians(CURRENT_DESTINATION['coordinates']['latitude'])
                lng2 = math.radians(CURRENT_DESTINATION['coordinates']['longitude'])
                
                dlat = lat2 - lat1
                dlng = lng2 - lng1
                a = (math.sin(dlat/2)**2 + 
                     math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2)
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                distance_to_destination = R * c
                
            except Exception as calc_error:
                print(f"Distance calculation error: {calc_error}")
        
        session_display = session_id.split('_')[-1] if '_' in session_id else session_id
        print(f"📍 Simple location [{session_display}]: {latitude:.6f}, {longitude:.6f}")
        if distance_to_destination:
            print(f"🎯 Distance to destination: {distance_to_destination:.1f}km")
        
        response_data = {
            "success": True,
            "message": "Location received",
            "session_id": session_id,
            "received_at": location_record["server_received_at"],
            "total_locations": len(location_history[session_id])
        }
        
        if distance_to_destination is not None:
            response_data["distance_to_destination"] = {
                "kilometers": round(distance_to_destination, 3),
                "meters": round(distance_to_destination * 1000),
                "destination_name": CURRENT_DESTINATION['name']
            }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"❌ Error in simple location update: {str(e)}")
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
        
        location_record = {
            "session_id": data.get('session_id', 'anonymous'),
            "user_id": data.get('user_id', 'anonymous'),
            "location": location_data,
            "timestamp": data.get('timestamp', datetime.datetime.now().isoformat()),
            "server_received_at": datetime.datetime.now().isoformat()
        }
        
        session_key = data.get('session_id', 'anonymous')
        if session_key not in location_history:
            location_history[session_key] = []
        
        location_history[session_key].append(location_record)
        
        if len(location_history[session_key]) > 100:
            location_history[session_key] = location_history[session_key][-100:]
        
        distance_to_destination = None
        if CURRENT_DESTINATION:
            try:
                import math
                R = 6371
                lat1 = math.radians(location_data['latitude'])
                lng1 = math.radians(location_data['longitude'])
                lat2 = math.radians(CURRENT_DESTINATION['coordinates']['latitude'])
                lng2 = math.radians(CURRENT_DESTINATION['coordinates']['longitude'])
                
                dlat = lat2 - lat1
                dlng = lng2 - lng1
                a = (math.sin(dlat/2)**2 + 
                     math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2)
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                distance_to_destination = R * c
                
            except Exception as calc_error:
                print(f"Distance calculation error: {calc_error}")
        
        session_display = session_key.split('_')[-1] if '_' in session_key else session_key
        print(f"📍 Location update [{session_display}]: {location_data['latitude']:.6f}, {location_data['longitude']:.6f}")
        if distance_to_destination:
            print(f"🎯 Distance to destination: {distance_to_destination:.1f}km ({distance_to_destination*1000:.0f}m)")
        
        response_data = {
            "success": True,
            "message": "Location updated successfully",
            "session_id": session_key,
            "received_at": location_record["server_received_at"]
        }
        
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
        
        if history:
            total_points = len(history)
            first_location = history[0]
            last_location = history[-1]
            
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
            "is_recent": seconds_since_update < 30 if seconds_since_update else False
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/location/all', methods=['GET'])
def get_all_locations():
    """Get all location data across all sessions"""
    try:
        limit = request.args.get('limit', type=int)
        
        all_locations = []
        for session_id, locations in location_history.items():
            for loc in locations:
                all_locations.append(loc)
        
        # Sort by timestamp (most recent first)
        all_locations.sort(key=lambda x: x.get('server_received_at', ''), reverse=True)
        
        if limit:
            all_locations = all_locations[:limit]
        
        return jsonify({
            "success": True,
            "locations": all_locations,
            "total_locations": len(all_locations),
            "total_sessions": len(location_history),
            "sessions": list(location_history.keys())
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/location/sessions', methods=['GET'])
def get_location_sessions():
    """Get summary of all sessions with location data"""
    try:
        sessions_summary = []
        
        for session_id, locations in location_history.items():
            if locations:
                first_loc = locations[0]
                last_loc = locations[-1]
                
                summary = {
                    "session_id": session_id,
                    "total_points": len(locations),
                    "first_location": first_loc,
                    "last_location": last_loc,
                    "time_span": {
                        "start": first_loc.get('timestamp'),
                        "end": last_loc.get('timestamp')
                    }
                }
                sessions_summary.append(summary)
        
        return jsonify({
            "success": True,
            "sessions": sessions_summary,
            "total_sessions": len(sessions_summary),
            "total_location_points": sum(len(locs) for locs in location_history.values())
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
    """Start a new navigation session for blind navigation"""
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
            "location_tracking_enabled": True
        }
        
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


@app.route('/api/navigation/step-active', methods=['POST'])
def step_active():
    """
    🆕 NEW ENDPOINT - Receive notification when a new step becomes active
    Expected data: {
        "session_id": "unique_session_id",
        "step_index": int,
        "step_instruction": "string",
        "step_distance": "string",
        "step_duration": "string",
        "current_location": {"latitude": float, "longitude": float},
        "maneuver": "string" (optional)
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
        
        if not all([session_id, step_index is not None, step_instruction]):
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400
        
        if session_id not in navigation_sessions:
            return jsonify({
                "success": False,
                "error": "Navigation session not found"
            }), 404
        
        active_step_record = {
            "session_id": session_id,
            "step_index": step_index,
            "step_instruction": step_instruction,
            "step_distance": data.get('step_distance', 'N/A'),
            "step_duration": data.get('step_duration', 'N/A'),
            "maneuver": data.get('maneuver'),
            "current_location": data.get('current_location'),
            "activated_at": datetime.datetime.now().isoformat(),
            "user_type": "blind_navigation"
        }
        
        active_steps.append(active_step_record)
        
        destination_name = navigation_sessions[session_id]['destination']['name']
        
        print(f"🔔 NEW STEP ACTIVE - BLIND NAVIGATION")
        print(f"🎯 Destination: {destination_name}")
        print(f"📋 Session: {session_id}")
        print(f"📍 Step {step_index + 1}: {step_instruction}")
        print(f"📏 Distance: {data.get('step_distance', 'N/A')}")
        print(f"⏱️  Duration: {data.get('step_duration', 'N/A')}")
        if data.get('maneuver'):
            print(f"🔄 Maneuver: {data.get('maneuver')}")
        if data.get('current_location'):
            loc = data.get('current_location')
            print(f"📍 Current location: {loc['latitude']:.6f}, {loc['longitude']:.6f}")
        print("=" * 60)
        
        total_steps = navigation_sessions[session_id].get('total_steps', 1)
        steps_remaining = total_steps - step_index
        
        return jsonify({
            "success": True,
            "message": f"Step {step_index + 1} is now active",
            "step_index": step_index,
            "destination_name": destination_name,
            "steps_remaining": steps_remaining,
            "voice_announcement": f"{step_instruction}. {data.get('step_distance', '')}",
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error processing active step: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/navigation/step-completed', methods=['POST'])
def step_completed():
    """Receive step completion notification for blind navigation"""
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
        
        if session_id not in navigation_sessions:
            return jsonify({
                "success": False,
                "error": "Navigation session not found"
            }), 404
        
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
        
        completed_steps.append(step_completion)
        
        navigation_sessions[session_id]['completed_steps'] = step_index + 1
        navigation_sessions[session_id]['last_update'] = datetime.datetime.now().isoformat()
        
        destination_name = navigation_sessions[session_id]['destination']['name']
        
        print(f"✅ STEP {step_index + 1} COMPLETED - BLIND NAVIGATION")
        print(f"🎯 Destination: {destination_name}")
        print(f"📋 Session: {session_id}")
        print(f"🗣️  Instruction completed: {step_instruction}")
        print(f"📍 Current location: {current_location['latitude']:.6f}, {current_location['longitude']:.6f}")
        print(f"🎯 GPS accuracy: {data.get('accuracy', 'Unknown')}m")
        print(f"⏱️  Completed at: {step_completion['completion_time']}")
        print("=" * 60)
        
        total_steps = navigation_sessions[session_id].get('total_steps', 1)
        progress_percentage = ((step_index + 1) / total_steps) * 100
        steps_remaining = total_steps - (step_index + 1)
        
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
    """Mark blind navigation as completed"""
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
        
        navigation_sessions[session_id]['status'] = 'completed'
        navigation_sessions[session_id]['completed_at'] = datetime.datetime.now().isoformat()
        navigation_sessions[session_id]['final_location'] = data.get('final_location')
        navigation_sessions[session_id]['actual_total_time'] = data.get('total_time')
        navigation_sessions[session_id]['actual_distance_traveled'] = data.get('total_distance_traveled')
        navigation_sessions[session_id]['location_tracking_enabled'] = False
        
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
        session_active_steps = [step for step in active_steps if step['session_id'] == session_id]
        
        location_tracking_info = {
            "enabled": session.get('location_tracking_enabled', False),
            "total_location_points": len(location_history.get(session_id, [])),
            "latest_location": location_history[session_id][-1] if session_id in location_history and location_history[session_id] else None
        }
        
        return jsonify({
            "success": True,
            "session": session,
            "completed_steps_detail": session_steps,
            "active_steps_detail": session_active_steps,
            "location_tracking": location_tracking_info,
            "summary": {
                "total_steps": session.get('total_steps', 0),
                "completed_steps": len(session_steps),
                "active_steps": len(session_active_steps),
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
            "total_active_steps": len(active_steps),
            "total_location_points": sum(len(history) for history in location_history.values()),
            "active_location_tracking_sessions": len([s for s in navigation_sessions.values() if s.get('location_tracking_enabled', False)]),
            "current_destination": CURRENT_DESTINATION['name']
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/navigation/progress/<session_id>', methods=['GET'])
def get_navigation_progress(session_id):
    """Get detailed navigation progress for a session"""
    try:
        if session_id not in navigation_sessions:
            return jsonify({
                "success": False,
                "error": "Navigation session not found"
            }), 404
        
        session = navigation_sessions[session_id]
        session_active = [step for step in active_steps if step['session_id'] == session_id]
        session_completed = [step for step in completed_steps if step['session_id'] == session_id]
        
        total_steps = session.get('total_steps', 0)
        completed_count = len(session_completed)
        progress_percentage = (completed_count / total_steps * 100) if total_steps > 0 else 0
        
        latest_location = None
        if session_id in location_history and location_history[session_id]:
            latest_location = location_history[session_id][-1]
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "destination": session['destination'],
            "progress": {
                "total_steps": total_steps,
                "completed_steps": completed_count,
                "active_steps": len(session_active),
                "remaining_steps": total_steps - completed_count,
                "percentage": round(progress_percentage, 1)
            },
            "latest_active_step": session_active[-1] if session_active else None,
            "latest_completed_step": session_completed[-1] if session_completed else None,
            "latest_location": latest_location,
            "status": session.get('status', 'unknown'),
            "started_at": session.get('started_at'),
            "completed_at": session.get('completed_at')
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/steps/active', methods=['GET'])
def get_all_active_steps():
    """Get all active steps across all sessions"""
    try:
        session_id = request.args.get('session_id')
        
        if session_id:
            # Filter by session_id if provided
            session_steps = [step for step in active_steps if step['session_id'] == session_id]
            return jsonify({
                "success": True,
                "session_id": session_id,
                "active_steps": session_steps,
                "total_active_steps": len(session_steps)
            }), 200
        else:
            # Return all active steps
            return jsonify({
                "success": True,
                "active_steps": active_steps,
                "total_active_steps": len(active_steps),
                "sessions_with_active_steps": len(set(step['session_id'] for step in active_steps))
            }), 200
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/steps/completed', methods=['GET'])
def get_all_completed_steps():
    """Get all completed steps across all sessions"""
    try:
        session_id = request.args.get('session_id')
        
        if session_id:
            # Filter by session_id if provided
            session_steps = [step for step in completed_steps if step['session_id'] == session_id]
            return jsonify({
                "success": True,
                "session_id": session_id,
                "completed_steps": session_steps,
                "total_completed_steps": len(session_steps)
            }), 200
        else:
            # Return all completed steps
            return jsonify({
                "success": True,
                "completed_steps": completed_steps,
                "total_completed_steps": len(completed_steps),
                "sessions_with_completed_steps": len(set(step['session_id'] for step in completed_steps))
            }), 200
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/steps/latest/<session_id>', methods=['GET'])
def get_latest_step(session_id):
    """Get the latest active or completed step for a session"""
    try:
        # Get latest active step
        session_active = [step for step in active_steps if step['session_id'] == session_id]
        latest_active = session_active[-1] if session_active else None
        
        # Get latest completed step
        session_completed = [step for step in completed_steps if step['session_id'] == session_id]
        latest_completed = session_completed[-1] if session_completed else None
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "latest_active_step": latest_active,
            "latest_completed_step": latest_completed,
            "total_active_steps": len(session_active),
            "total_completed_steps": len(session_completed)
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/analytics/summary', methods=['GET'])
def get_analytics_summary():
    """Get overall analytics and summary of all navigation data"""
    try:
        total_sessions = len(navigation_sessions)
        active_sessions = len([s for s in navigation_sessions.values() if s.get('status') == 'active'])
        completed_sessions = len([s for s in navigation_sessions.values() if s.get('status') == 'completed'])
        
        total_location_points = sum(len(locs) for locs in location_history.values())
        sessions_with_locations = len(location_history)
        
        return jsonify({
            "success": True,
            "summary": {
                "sessions": {
                    "total": total_sessions,
                    "active": active_sessions,
                    "completed": completed_sessions
                },
                "steps": {
                    "total_active": len(active_steps),
                    "total_completed": len(completed_steps)
                },
                "locations": {
                    "total_points": total_location_points,
                    "sessions_tracked": sessions_with_locations
                },
                "current_destination": CURRENT_DESTINATION
            },
            "timestamp": datetime.datetime.now().isoformat()
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


if __name__ == '__main__':
    print("🚀 Starting Blind Navigation API Server...")
    print("🔊 Optimized for blind users - voice navigation")
    print(f"🎯 Current destination: {CURRENT_DESTINATION['name']}")
    print(f"📍 Coordinates: {CURRENT_DESTINATION['coordinates']['latitude']}, {CURRENT_DESTINATION['coordinates']['longitude']}")
    print("📡 Listening for navigation requests...")
    print("📍 Location tracking enabled")
    print("\n🔗 API Endpoints:")
    print("\n📍 Destination Endpoints:")
    print("   GET  /api/destination - Get current destination")
    print("   POST /api/destination/update - Update destination (admin)")
    print("\n📡 Location Endpoints:")
    print("   POST /api/location/update - Receive detailed location updates")
    print("   POST /api/location/simple - Receive simple location updates")
    print("   GET  /api/location/history/<session_id> - Get location history")
    print("   GET  /api/location/current/<session_id> - Get current location")
    print("   GET  /api/location/all - Get all locations (optional ?limit=N)")
    print("   GET  /api/location/sessions - Get location sessions summary")
    print("\n🚶 Navigation Endpoints:")
    print("   POST /api/navigation/start - Start navigation session")
    print("   POST /api/navigation/step-active - New step active")
    print("   POST /api/navigation/step-completed - Step completion notification")
    print("   POST /api/navigation/complete - Mark navigation complete")
    print("   GET  /api/navigation/status/<session_id> - Get session status")
    print("   GET  /api/navigation/sessions - Get all sessions")
    print("   GET  /api/navigation/progress/<session_id> - Get navigation progress")
    print("\n👣 Step Endpoints:")
    print("   GET  /api/steps/active - Get all active steps (optional ?session_id=X)")
    print("   GET  /api/steps/completed - Get all completed steps (optional ?session_id=X)")
    print("   GET  /api/steps/latest/<session_id> - Get latest step info")
    print("\n📊 Analytics & Health:")
    print("   GET  /api/analytics/summary - Get overall analytics summary")
    print("   GET  /api/health - Health check")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    # Run the server
    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=port,       # Port 5000
        debug=False       # Enable debug mode
    )





