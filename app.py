from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime
import json
import os

app = Flask(__name__)
CORS(app)

# Add request logging middleware
@app.before_request
def log_request():
    """Log all incoming requests for debugging"""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"\n{'='*60}")
    print(f"📨 [{timestamp}] {request.method} {request.path}")
    print(f"{'='*60}")
    
    if request.method == 'POST' and request.get_json():
        print(f"📦 Request Body:")
        print(json.dumps(request.get_json(), indent=2))
    
    if request.args:
        print(f"🔍 Query Params: {dict(request.args)}")

# Global state - no sessions needed
current_navigation = {
    "is_active": False,
    "destination": None,
    "user_location": None,
    "current_step": 0,
    "total_steps": 0,
    "started_at": None,
    "completed_steps": []
}

location_updates = []
active_step = None
completed_steps = []

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


def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two coordinates in kilometers"""
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlng/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


@app.route('/api/destination', methods=['GET'])
def get_current_destination():
    """Get the current active destination"""
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
            
            distance = calculate_distance(lat, lng, dest_lat, dest_lng)
            
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


@app.route('/api/destination/update', methods=['POST'])
def update_destination():
    """Update the current destination"""
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


@app.route('/api/location/update', methods=['POST'])
def update_location():
    """Receive location updates from the app"""
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
            "location": location_data,
            "timestamp": data.get('timestamp', datetime.datetime.now().isoformat()),
            "server_received_at": datetime.datetime.now().isoformat()
        }
        
        location_updates.append(location_record)
        
        # Keep only last 100 locations
        if len(location_updates) > 100:
            location_updates[:] = location_updates[-100:]
        
        # Update global navigation state
        current_navigation["user_location"] = {
            "latitude": location_data['latitude'],
            "longitude": location_data['longitude']
        }
        
        # Calculate distance to destination
        distance_to_destination = None
        if CURRENT_DESTINATION:
            try:
                distance_to_destination = calculate_distance(
                    location_data['latitude'],
                    location_data['longitude'],
                    CURRENT_DESTINATION['coordinates']['latitude'],
                    CURRENT_DESTINATION['coordinates']['longitude']
                )
            except Exception as calc_error:
                print(f"Distance calculation error: {calc_error}")
        
        print(f"📍 Location update: {location_data['latitude']:.6f}, {location_data['longitude']:.6f}")
        if distance_to_destination:
            print(f"🎯 Distance to destination: {distance_to_destination:.1f}km ({distance_to_destination*1000:.0f}m)")
        
        response_data = {
            "success": True,
            "message": "Location updated successfully",
            "received_at": location_record["server_received_at"],
            "total_updates": len(location_updates)
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


@app.route('/api/location/current', methods=['GET'])
def get_current_location():
    """Get the most recent location"""
    try:
        if not location_updates:
            return jsonify({
                "success": False,
                "error": "No location data available"
            }), 404
        
        latest_location = location_updates[-1]
        
        try:
            last_update = datetime.datetime.fromisoformat(latest_location['server_received_at'].replace('Z', '+00:00'))
            time_since_update = datetime.datetime.now() - last_update
            seconds_since_update = time_since_update.total_seconds()
        except:
            seconds_since_update = None
        
        return jsonify({
            "success": True,
            "current_location": latest_location,
            "seconds_since_last_update": seconds_since_update,
            "is_recent": seconds_since_update < 30 if seconds_since_update else False
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/location/history', methods=['GET'])
def get_location_history():
    """Get all location history"""
    try:
        limit = request.args.get('limit', type=int)
        
        history = location_updates if not limit else location_updates[-limit:]
        
        total_distance = 0
        if len(history) > 1:
            for i in range(1, len(history)):
                prev_loc = history[i-1]['location']
                curr_loc = history[i]['location']
                
                try:
                    total_distance += calculate_distance(
                        prev_loc['latitude'], prev_loc['longitude'],
                        curr_loc['latitude'], curr_loc['longitude']
                    )
                except:
                    pass
        
        return jsonify({
            "success": True,
            "location_history": history,
            "stats": {
                "total_points": len(history),
                "total_distance_km": round(total_distance, 3),
                "first_location": history[0] if history else None,
                "last_location": history[-1] if history else None
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/navigation/start', methods=['POST'])
def start_navigation():
    """Start navigation"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        global current_navigation
        current_navigation = {
            "is_active": True,
            "destination": CURRENT_DESTINATION.copy(),
            "user_location": data.get('user_location'),
            "total_steps": data.get('total_steps', 0),
            "current_step": 0,
            "total_distance": data.get('total_distance'),
            "total_duration": data.get('total_duration'),
            "started_at": datetime.datetime.now().isoformat(),
            "completed_steps": []
        }
        
        print(f"🚀 NAVIGATION STARTED")
        print(f"🎯 Destination: {CURRENT_DESTINATION['name']}")
        print(f"📍 From: {data.get('user_location')}")
        print(f"📊 Route: {data.get('total_steps')} steps, {data.get('total_distance')}")
        print("=" * 60)
        
        return jsonify({
            "success": True,
            "message": f"Navigation started to {CURRENT_DESTINATION['name']}",
            "destination_name": CURRENT_DESTINATION['name'],
            "voice_announcement": f"Navigation started. Proceeding to {CURRENT_DESTINATION['name']}. {data.get('total_distance')} ahead.",
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error starting navigation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/navigation/step-active', methods=['POST'])
def step_active():
    """Receive notification when a new step becomes active"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        step_index = data.get('step_index')
        step_instruction = data.get('step_instruction')
        
        if step_index is None or not step_instruction:
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400
        
        global active_step
        active_step = {
            "step_index": step_index,
            "step_instruction": step_instruction,
            "step_distance": data.get('step_distance', 'N/A'),
            "step_duration": data.get('step_duration', 'N/A'),
            "maneuver": data.get('maneuver'),
            "current_location": data.get('current_location'),
            "activated_at": datetime.datetime.now().isoformat()
        }
        
        # Update global navigation state
        current_navigation["current_step"] = step_index
        
        destination_name = CURRENT_DESTINATION['name']
        
        print(f"🔔 NEW STEP ACTIVE")
        print(f"🎯 Destination: {destination_name}")
        print(f"📍 Step {step_index + 1}: {step_instruction}")
        print(f"📏 Distance: {data.get('step_distance', 'N/A')}")
        print(f"⏱️  Duration: {data.get('step_duration', 'N/A')}")
        if data.get('current_location'):
            loc = data.get('current_location')
            print(f"📍 Current location: {loc['latitude']:.6f}, {loc['longitude']:.6f}")
        print("=" * 60)
        
        total_steps = current_navigation.get('total_steps', 1)
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
    """Receive step completion notification"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        step_index = data.get('step_index')
        step_instruction = data.get('step_instruction')
        current_location = data.get('current_location')
        
        if step_index is None or not step_instruction or not current_location:
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400
        
        step_completion = {
            "step_index": step_index,
            "step_instruction": step_instruction,
            "step_distance": data.get('step_distance', 'N/A'),
            "current_location": current_location,
            "completion_time": datetime.datetime.now().isoformat(),
            "accuracy": data.get('accuracy')
        }
        
        completed_steps.append(step_completion)
        current_navigation["completed_steps"].append(step_completion)
        
        destination_name = CURRENT_DESTINATION['name']
        
        print(f"✅ STEP {step_index + 1} COMPLETED")
        print(f"🎯 Destination: {destination_name}")
        print(f"🗣️  Instruction completed: {step_instruction}")
        print(f"📍 Current location: {current_location['latitude']:.6f}, {current_location['longitude']:.6f}")
        print(f"🎯 GPS accuracy: {data.get('accuracy', 'Unknown')}m")
        print("=" * 60)
        
        total_steps = current_navigation.get('total_steps', 1)
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
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error processing step completion: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/navigation/complete', methods=['POST'])
def navigation_complete():
    """Mark navigation as completed"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        destination_name = CURRENT_DESTINATION['name']
        
        current_navigation['is_active'] = False
        current_navigation['completed_at'] = datetime.datetime.now().isoformat()
        current_navigation['final_location'] = data.get('final_location')
        current_navigation['actual_total_time'] = data.get('total_time')
        current_navigation['actual_distance_traveled'] = data.get('total_distance_traveled')
        
        print(f"🎉 NAVIGATION COMPLETED!")
        print(f"🎯 Destination: {destination_name}")
        print(f"📍 Final location: {data.get('final_location')}")
        print(f"⏱️  Total time: {data.get('total_time', 'N/A')}")
        print(f"🛣️  Distance traveled: {data.get('total_distance_traveled', 'N/A')}km")
        print("=" * 60)
        
        return jsonify({
            "success": True,
            "message": f"Navigation to {destination_name} completed successfully",
            "destination_name": destination_name,
            "voice_announcement": f"Navigation complete. You have successfully arrived at {destination_name}.",
            "summary": {
                "destination": destination_name,
                "total_steps_completed": len(current_navigation['completed_steps']),
                "actual_time": data.get('total_time'),
                "actual_distance": data.get('total_distance_traveled'),
                "completed_at": current_navigation['completed_at']
            },
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error completing navigation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/navigation/status', methods=['GET'])
def get_navigation_status():
    """Get current navigation status"""
    try:
        return jsonify({
            "success": True,
            "navigation": current_navigation,
            "active_step": active_step,
            "completed_steps_count": len(completed_steps),
            "latest_completed_step": completed_steps[-1] if completed_steps else None,
            "latest_location": location_updates[-1] if location_updates else None,
            "destination": CURRENT_DESTINATION
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/steps/active', methods=['GET'])
def get_active_step():
    """Get current active step"""
    try:
        return jsonify({
            "success": True,
            "active_step": active_step,
            "current_step_index": current_navigation.get('current_step', 0),
            "total_steps": current_navigation.get('total_steps', 0)
        }), 200
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/steps/completed', methods=['GET'])
def get_completed_steps():
    """Get all completed steps"""
    try:
        return jsonify({
            "success": True,
            "completed_steps": completed_steps,
            "total_completed": len(completed_steps)
        }), 200
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/analytics/summary', methods=['GET'])
def get_analytics_summary():
    """Get overall analytics summary"""
    try:
        return jsonify({
            "success": True,
            "summary": {
                "navigation": {
                    "is_active": current_navigation.get('is_active', False),
                    "current_step": current_navigation.get('current_step', 0),
                    "total_steps": current_navigation.get('total_steps', 0),
                    "completed_steps": len(completed_steps)
                },
                "locations": {
                    "total_points": len(location_updates),
                    "latest_update": location_updates[-1] if location_updates else None
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
        "message": "Navigation API is running!",
        "timestamp": datetime.datetime.now().isoformat(),
        "navigation_active": current_navigation.get('is_active', False),
        "total_location_points": len(location_updates),
        "current_destination": CURRENT_DESTINATION['name'],
        "service_type": "blind_navigation"
    }), 200


if __name__ == '__main__':
    print("🚀 Starting Navigation API Server (Session-less)...")
    print("🔊 Optimized for blind users - voice navigation")
    print(f"🎯 Current destination: {CURRENT_DESTINATION['name']}")
    print(f"📍 Coordinates: {CURRENT_DESTINATION['coordinates']['latitude']}, {CURRENT_DESTINATION['coordinates']['longitude']}")
    print("📡 Ready for navigation requests...")
    print("\n🔗 API Endpoints:")
    print("\n📍 Destination:")
    print("   GET  /api/destination - Get current destination")
    print("   POST /api/destination/update - Update destination")
    print("\n📡 Location:")
    print("   POST /api/location/update - Update location")
    print("   GET  /api/location/current - Get current location")
    print("   GET  /api/location/history - Get location history")
    print("\n🚶 Navigation:")
    print("   POST /api/navigation/start - Start navigation")
    print("   POST /api/navigation/step-active - New step active")
    print("   POST /api/navigation/step-completed - Step completed")
    print("   POST /api/navigation/complete - Navigation complete")
    print("   GET  /api/navigation/status - Get navigation status")
    print("\n👣 Steps:")
    print("   GET  /api/steps/active - Get active step")
    print("   GET  /api/steps/completed - Get completed steps")
    print("\n📊 Analytics:")
    print("   GET  /api/analytics/summary - Get summary")
    print("   GET  /api/health - Health check")
    print("=" * 60)
    port = int(os.environ.get('PORT', 5000))
    # Run the server
    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=port,       # Port 5000
        debug=False       # Enable debug mode
    )






