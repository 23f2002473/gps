from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime
import json
import os
import time
from collections import defaultdict
import threading

app = Flask(__name__)
CORS(app)  # Enable CORS for React Native requests

# Enhanced data storage
navigation_sessions = {}
completed_steps = []
location_history = defaultdict(list)  # More efficient for multiple sessions
location_stats = defaultdict(dict)  # Store stats per session
api_request_logs = []  # Track API usage

# Rate limiting and throttling
last_location_update = defaultdict(float)  # Track last update time per session
location_update_counts = defaultdict(int)  # Count updates per session
LOCATION_UPDATE_THROTTLE = 2.0  # Minimum seconds between updates per session

# Single destination configuration - modify this as needed


def log_api_request(endpoint, method, session_id=None, status="success", error=None):
    """Log API requests for monitoring"""
    log_entry = {
        "endpoint": endpoint,
        "method": method,
        "session_id": session_id,
        "status": status,
        "error": error,
        "timestamp": datetime.datetime.now().isoformat(),
        "ip": request.remote_addr if request else None
    }
    api_request_logs.append(log_entry)
    
    # Keep only last 1000 logs to prevent memory issues
    if len(api_request_logs) > 1000:
        api_request_logs.pop(0)

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two coordinates using Haversine formula"""
    import math
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlng/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def update_location_stats(session_id, location_data):
    """Update location statistics for a session"""
    if session_id not in location_stats:
        location_stats[session_id] = {
            "first_location": location_data,
            "last_location": location_data,
            "total_distance": 0,
            "total_updates": 0,
            "average_accuracy": 0,
            "speed_records": []
        }
    
    stats = location_stats[session_id]
    
    # Calculate distance traveled
    if stats["total_updates"] > 0:
        prev_loc = stats["last_location"]
        distance = calculate_distance(
            prev_loc['latitude'], prev_loc['longitude'],
            location_data['latitude'], location_data['longitude']
        )
        stats["total_distance"] += distance
    
    # Update stats
    stats["last_location"] = location_data
    stats["total_updates"] += 1
    
    # Update average accuracy
    if location_data.get('accuracy'):
        current_avg = stats["average_accuracy"]
        count = stats["total_updates"]
        stats["average_accuracy"] = ((current_avg * (count - 1)) + location_data['accuracy']) / count
    
    # Track speed if available
    if location_data.get('speed') is not None and location_data['speed'] > 0:
        stats["speed_records"].append({
            "speed": location_data['speed'],
            "timestamp": datetime.datetime.now().isoformat()
        })
        # Keep only last 50 speed records
        if len(stats["speed_records"]) > 50:
            stats["speed_records"].pop(0)

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
            log_api_request('/api/destination', 'GET', status="error", error="Missing user_location")
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
            
            distance = calculate_distance(lat, lng, dest_lat, dest_lng)
            
            destination['calculated_distance'] = f"{distance:.1f} km"
            destination['calculated_time'] = f"{max(5, int(distance * 3))} min"  # Walking estimate
            destination['distance_meters'] = int(distance * 1000)
            
        except Exception as calc_error:
            print(f"Distance calculation error: {calc_error}")
            # Keep original values if calculation fails
        
        print(f"📍 Destination requested for blind navigation: {destination['name']}")
        print(f"🎯 Distance: {destination.get('calculated_distance', destination['distance'])}")
        
        log_api_request('/api/destination', 'GET', status="success")
        
        return jsonify({
            "success": True,
            "destination": destination,
            "auto_start": True,  # Signal that navigation should start automatically
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching destination: {str(e)}")
        log_api_request('/api/destination', 'GET', status="error", error=str(e))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/location/update', methods=['POST'])
def update_location():
    """
    Enhanced location update endpoint with throttling and stats
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
            log_api_request('/api/location/update', 'POST', status="error", error="No data provided")
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        location_data = data.get('location')
        if not location_data or 'latitude' not in location_data or 'longitude' not in location_data:
            log_api_request('/api/location/update', 'POST', status="error", error="Invalid location data")
            return jsonify({
                "success": False,
                "error": "Location data with latitude and longitude required"
            }), 400
        
        session_id = data.get('session_id', 'anonymous')
        current_time = time.time()
        
        # Enhanced throttling - prevent spam updates
        if session_id in last_location_update:
            time_since_last = current_time - last_location_update[session_id]
            if time_since_last < LOCATION_UPDATE_THROTTLE:
                return jsonify({
                    "success": False,
                    "error": f"Update throttled. Wait {LOCATION_UPDATE_THROTTLE - time_since_last:.1f}s",
                    "throttle_remaining": LOCATION_UPDATE_THROTTLE - time_since_last
                }), 429
        
        # Update throttling tracker
        last_location_update[session_id] = current_time
        location_update_counts[session_id] = location_update_counts.get(session_id, 0) + 1
        
        # Create enhanced location record
        location_record = {
            "session_id": session_id,
            "user_id": data.get('user_id', 'anonymous'),
            "location": location_data,
            "timestamp": data.get('timestamp', datetime.datetime.now().isoformat()),
            "server_received_at": datetime.datetime.now().isoformat(),
            "update_count": location_update_counts[session_id],
            "time_since_last": time_since_last if session_id in last_location_update else 0
        }
        
        # Store in location history
        location_history[session_id].append(location_record)
        
        # Keep only last 200 locations per session to prevent memory issues
        if len(location_history[session_id]) > 200:
            location_history[session_id] = location_history[session_id][-200:]
        
        # Update location statistics
        update_location_stats(session_id, location_data)
        
        # Calculate distance to destination if available
        distance_to_destination = None
        if CURRENT_DESTINATION:
            try:
                distance_to_destination = calculate_distance(
                    location_data['latitude'], location_data['longitude'],
                    CURRENT_DESTINATION['coordinates']['latitude'],
                    CURRENT_DESTINATION['coordinates']['longitude']
                )
            except Exception as calc_error:
                print(f"Distance calculation error: {calc_error}")
        
        # Enhanced logging (less verbose to avoid spam)
        if location_update_counts[session_id] % 5 == 1:  # Log every 5th update
            print(f"📍 Location update #{location_update_counts[session_id]}: {location_data['latitude']:.6f}, {location_data['longitude']:.6f}")
            if distance_to_destination:
                print(f"🎯 Distance to destination: {distance_to_destination:.1f}km")
        
        log_api_request('/api/location/update', 'POST', session_id=session_id, status="success")
        
        response_data = {
            "success": True,
            "message": "Location updated successfully",
            "session_id": session_id,
            "received_at": location_record["server_received_at"],
            "update_count": location_update_counts[session_id],
            "session_stats": {
                "total_updates": location_stats[session_id]["total_updates"] if session_id in location_stats else 0,
                "total_distance_km": round(location_stats[session_id]["total_distance"], 3) if session_id in location_stats else 0
            }
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
        log_api_request('/api/location/update', 'POST', 
                       session_id=data.get('session_id') if 'data' in locals() else None, 
                       status="error", error=str(e))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/location/bulk-update', methods=['POST'])
def bulk_update_location():
    """
    Handle bulk location updates for offline sync
    Expected data: {
        "session_id": "session_id",
        "locations": [
            {
                "location": {...},
                "timestamp": "..."
            }
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'locations' not in data:
            return jsonify({
                "success": False,
                "error": "locations array required"
            }), 400
        
        session_id = data.get('session_id', 'anonymous')
        locations = data.get('locations', [])
        
        if len(locations) > 50:  # Limit bulk updates
            return jsonify({
                "success": False,
                "error": "Maximum 50 locations per bulk update"
            }), 400
        
        processed_count = 0
        for loc_data in locations:
            if 'location' in loc_data:
                location_record = {
                    "session_id": session_id,
                    "location": loc_data['location'],
                    "timestamp": loc_data.get('timestamp', datetime.datetime.now().isoformat()),
                    "server_received_at": datetime.datetime.now().isoformat(),
                    "bulk_update": True
                }
                
                location_history[session_id].append(location_record)
                update_location_stats(session_id, loc_data['location'])
                processed_count += 1
        
        print(f"📍 Bulk update: {processed_count} locations processed for session {session_id}")
        
        log_api_request('/api/location/bulk-update', 'POST', session_id=session_id, status="success")
        
        return jsonify({
            "success": True,
            "message": f"Processed {processed_count} location updates",
            "session_id": session_id,
            "processed_count": processed_count
        }), 200
        
    except Exception as e:
        print(f"❌ Error in bulk location update: {str(e)}")
        log_api_request('/api/location/bulk-update', 'POST', status="error", error=str(e))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/location/history/<session_id>', methods=['GET'])
def get_location_history(session_id):
    """Get enhanced location history for a specific session"""
    try:
        if session_id not in location_history:
            return jsonify({
                "success": False,
                "error": "No location history found for this session"
            }), 404
        
        history = location_history[session_id]
        stats = location_stats.get(session_id, {})
        
        # Calculate some basic stats
        if history:
            total_points = len(history)
            first_location = history[0]
            last_location = history[-1]
            
            # Get update frequency
            if len(history) > 1:
                time_span = datetime.datetime.fromisoformat(last_location['timestamp']) - datetime.datetime.fromisoformat(first_location['timestamp'])
                avg_interval = time_span.total_seconds() / (len(history) - 1) if len(history) > 1 else 0
            else:
                avg_interval = 0
        else:
            total_points = 0
            first_location = None
            last_location = None
            avg_interval = 0
        
        log_api_request('/api/location/history', 'GET', session_id=session_id, status="success")
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "location_history": history,
            "session_stats": stats,
            "summary": {
                "total_points": total_points,
                "total_distance_km": round(stats.get('total_distance', 0), 3),
                "average_accuracy_m": round(stats.get('average_accuracy', 0), 1),
                "average_update_interval_s": round(avg_interval, 1),
                "first_location": first_location,
                "last_location": last_location,
                "time_span": {
                    "start": first_location['timestamp'] if first_location else None,
                    "end": last_location['timestamp'] if last_location else None
                }
            }
        }), 200
        
    except Exception as e:
        log_api_request('/api/location/history', 'GET', session_id=session_id, status="error", error=str(e))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/location/current/<session_id>', methods=['GET'])
def get_current_location(session_id):
    """Get the most recent location for a session with enhanced info"""
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
        
        # Get session stats
        stats = location_stats.get(session_id, {})
        
        log_api_request('/api/location/current', 'GET', session_id=session_id, status="success")
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "current_location": latest_location,
            "seconds_since_last_update": seconds_since_update,
            "is_recent": seconds_since_update < 30 if seconds_since_update else False,
            "update_count": location_update_counts.get(session_id, 0),
            "session_stats": stats
        }), 200
        
    except Exception as e:
        log_api_request('/api/location/current', 'GET', session_id=session_id, status="error", error=str(e))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/location/stats/<session_id>', methods=['GET'])
def get_location_stats(session_id):
    """Get detailed location statistics for a session"""
    try:
        if session_id not in location_stats:
            return jsonify({
                "success": False,
                "error": "No statistics found for this session"
            }), 404
        
        stats = location_stats[session_id]
        history = location_history[session_id]
        
        # Calculate additional stats
        if len(history) > 1:
            # Calculate average speed
            speeds = [record['location'].get('speed', 0) for record in history if record['location'].get('speed', 0) > 0]
            avg_speed = sum(speeds) / len(speeds) if speeds else 0
            max_speed = max(speeds) if speeds else 0
            
            # Calculate update frequency
            timestamps = [datetime.datetime.fromisoformat(record['timestamp']) for record in history]
            intervals = [(timestamps[i] - timestamps[i-1]).total_seconds() for i in range(1, len(timestamps))]
            avg_interval = sum(intervals) / len(intervals) if intervals else 0
        else:
            avg_speed = 0
            max_speed = 0
            avg_interval = 0
        
        enhanced_stats = {
            **stats,
            "average_speed_ms": round(avg_speed, 2),
            "max_speed_ms": round(max_speed, 2),
            "average_update_interval_s": round(avg_interval, 2),
            "total_update_count": location_update_counts.get(session_id, 0),
            "current_destination": CURRENT_DESTINATION['name']
        }
        
        log_api_request('/api/location/stats', 'GET', session_id=session_id, status="success")
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "statistics": enhanced_stats
        }), 200
        
    except Exception as e:
        log_api_request('/api/location/stats', 'GET', session_id=session_id, status="error", error=str(e))
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
        
        log_api_request('/api/destination/update', 'POST', status="success")
        
        return jsonify({
            "success": True,
            "message": "Destination updated successfully",
            "destination": CURRENT_DESTINATION,
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error updating destination: {str(e)}")
        log_api_request('/api/destination/update', 'POST', status="error", error=str(e))
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
            "location_tracking_enabled": True
        }
        
        # Initialize location history for this session if not exists
        if session_id not in location_history:
            location_history[session_id] = []
        
        # Initialize location stats
        if session_id not in location_stats:
            location_stats[session_id] = {
                "total_distance": 0,
                "total_updates": 0,
                "average_accuracy": 0,
                "speed_records": []
            }
        
        print(f"🚀 BLIND NAVIGATION STARTED")
        print(f"📋 Session: {session_id}")
        print(f"🎯 Destination: {CURRENT_DESTINATION['name']}")
        print(f"📍 From: {data.get('user_location')}")
        print(f"📊 Route: {data.get('total_steps')} steps, {data.get('total_distance')}, {data.get('total_duration')}")
        print(f"🔊 Voice navigation active")
        print(f"📍 Location tracking enabled")
        print("=" * 60)
        
        log_api_request('/api/navigation/start', 'POST', session_id=session_id, status="success")
        
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
        log_api_request('/api/navigation/start', 'POST', 
                       session_id=data.get('session_id') if 'data' in locals() else None, 
                       status="error", error=str(e))
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
        
        log_api_request('/api/navigation/step-completed', 'POST', session_id=session_id, status="success")
        
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
        log_api_request('/api/navigation/step-completed', 'POST', 
                       session_id=data.get('session_id') if 'data' in locals() else None, 
                       status="error", error=str(e))
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
        
        log_api_request('/api/navigation/complete', 'POST', session_id=session_id, status="success")
        
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
                "completed_at": navigation_sessions[session_id]['completed_at'],
                "location_updates": location_update_counts.get(session_id, 0),
                "total_distance_tracked": round(location_stats.get(session_id, {}).get('total_distance', 0), 3)
            },
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error completing blind navigation: {str(e)}")
        log_api_request('/api/navigation/complete', 'POST', 
                       session_id=data.get('session_id') if 'data' in locals() else None, 
                       status="error", error=str(e))
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
        
        # Get enhanced location tracking info
        location_tracking_info = {
            "enabled": session.get('location_tracking_enabled', False),
            "total_location_points": len(location_history.get(session_id, [])),
            "latest_location": location_history[session_id][-1] if session_id in location_history and location_history[session_id] else None,
            "update_count": location_update_counts.get(session_id, 0),
            "session_stats": location_stats.get(session_id, {})
        }
        
        log_api_request('/api/navigation/status', 'GET', session_id=session_id, status="success")
        
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
        log_api_request('/api/navigation/status', 'GET', session_id=session_id, status="error", error=str(e))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/sessions', methods=['GET'])
def get_all_sessions():
    """Get all blind navigation sessions with enhanced stats"""
    try:
        # Calculate aggregate stats
        total_location_points = sum(len(history) for history in location_history.values())
        active_tracking = len([s for s in navigation_sessions.values() if s.get('location_tracking_enabled', False)])
        
        # Get recent activity
        recent_updates = sum(1 for session_id in location_update_counts.keys() 
                           if session_id in last_location_update and 
                           time.time() - last_location_update[session_id] < 300)  # Last 5 minutes
        
        log_api_request('/api/navigation/sessions', 'GET', status="success")
        
        return jsonify({
            "success": True,
            "sessions": list(navigation_sessions.values()),
            "total_sessions": len(navigation_sessions),
            "total_completed_steps": len(completed_steps),
            "total_location_points": total_location_points,
            "active_location_tracking_sessions": active_tracking,
            "recent_activity_sessions": recent_updates,
            "current_destination": CURRENT_DESTINATION['name'],
            "system_stats": {
                "total_api_requests": len(api_request_logs),
                "active_sessions": len([s for s in navigation_sessions.values() if s.get('status') == 'active']),
                "completed_sessions": len([s for s in navigation_sessions.values() if s.get('status') == 'completed']),
                "uptime_info": "Server running"
            }
        }), 200
    except Exception as e:
        log_api_request('/api/navigation/sessions', 'GET', status="error", error=str(e))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/system/stats', methods=['GET'])
def get_system_stats():
    """Get detailed system statistics"""
    try:
        # Calculate comprehensive stats
        total_sessions = len(navigation_sessions)
        active_sessions = len([s for s in navigation_sessions.values() if s.get('status') == 'active'])
        completed_sessions = len([s for s in navigation_sessions.values() if s.get('status') == 'completed'])
        
        total_location_updates = sum(location_update_counts.values())
        unique_sessions_with_location = len(location_history)
        
        # API usage stats
        api_success_rate = len([log for log in api_request_logs if log['status'] == 'success']) / len(api_request_logs) * 100 if api_request_logs else 0
        
        # Recent activity (last hour)
        recent_time = time.time() - 3600  # 1 hour ago
        recent_updates = sum(1 for session_id in last_location_update.keys() 
                           if last_location_update[session_id] > recent_time)
        
        return jsonify({
            "success": True,
            "system_statistics": {
                "navigation": {
                    "total_sessions": total_sessions,
                    "active_sessions": active_sessions,
                    "completed_sessions": completed_sessions,
                    "completion_rate": round(completed_sessions / total_sessions * 100, 1) if total_sessions > 0 else 0
                },
                "location_tracking": {
                    "total_location_updates": total_location_updates,
                    "unique_tracked_sessions": unique_sessions_with_location,
                    "recent_updates_1h": recent_updates,
                    "average_updates_per_session": round(total_location_updates / unique_sessions_with_location, 1) if unique_sessions_with_location > 0 else 0
                },
                "api_performance": {
                    "total_requests": len(api_request_logs),
                    "success_rate": round(api_success_rate, 1),
                    "throttled_requests": len([log for log in api_request_logs if "throttled" in log.get('error', '').lower()])
                },
                "current_destination": CURRENT_DESTINATION['name'],
                "server_time": datetime.datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Enhanced health check endpoint"""
    try:
        # Calculate some health metrics
        total_sessions = len(navigation_sessions)
        active_tracking = len([s for s in navigation_sessions.values() if s.get('location_tracking_enabled', False)])
        total_location_points = sum(len(history) for history in location_history.values())
        
        # Recent activity check
        recent_activity = any(time.time() - last_update < 300 for last_update in last_location_update.values())
        
        health_status = {
            "success": True,
            "message": "Enhanced Blind Navigation API is running!",
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "healthy",
            "version": "2.0",
            "active_sessions": len([s for s in navigation_sessions.values() if s.get('status') == 'active']),
            "total_sessions": total_sessions,
            "location_tracking_sessions": active_tracking,
            "total_location_points": total_location_points,
            "recent_activity": recent_activity,
            "current_destination": CURRENT_DESTINATION['name'],
            "service_type": "enhanced_blind_navigation",
            "features": [
                "continuous_location_tracking",
                "bulk_location_updates", 
                "enhanced_statistics",
                "request_throttling",
                "comprehensive_logging"
            ]
        }
        
        log_api_request('/api/health', 'GET', status="success")
        
        return jsonify(health_status), 200
        
    except Exception as e:
        log_api_request('/api/health', 'GET', status="error", error=str(e))
        return jsonify({
            "success": False,
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    print("🚀 Starting Enhanced Blind Navigation API Server...")
    print("🔊 Optimized for blind users - voice navigation")
    print(f"🎯 Current destination: {CURRENT_DESTINATION['name']}")
    print("📡 Listening for navigation requests...")
    print("📍 Enhanced location tracking enabled")
    print("⚡ New features: bulk updates, enhanced stats, request throttling")
    print("🔗 API Endpoints:")
    print("   GET /api/destination - Get current destination")
    print("   POST /api/destination/update - Update destination (admin)")
    print("   POST /api/location/update - Receive location updates (enhanced)")
    print("   POST /api/location/bulk-update - Bulk location updates (NEW)")
    print("   GET /api/location/history/<session_id> - Get location history (enhanced)")
    print("   GET /api/location/current/<session_id> - Get current location (enhanced)")
    print("   GET /api/location/stats/<session_id> - Get location statistics (NEW)")
    print("   POST /api/navigation/start - Start navigation session")
    print("   POST /api/navigation/step-completed - Step completion notification")
    print("   POST /api/navigation/complete - Mark navigation complete")
    print("   GET /api/navigation/status/<session_id> - Get session status (enhanced)")
    print("   GET /api/navigation/sessions - Get all sessions (enhanced)")
    print("   GET /api/system/stats - Get system statistics (NEW)")
    print("   GET /api/health - Health check (enhanced)")
    print("=" * 60)
    
    # Run the server
    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=5000,       # Port 5000
        debug=True       # Enable debug mode
    )

