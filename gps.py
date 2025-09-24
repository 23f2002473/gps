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

@app.route('/api/navigation/start', methods=['POST'])
def start_navigation():
    """
    Start a new navigation session
    Expected data: {
        "session_id": "unique_session_id",
        "origin": {"latitude": float, "longitude": float},
        "destination": {"latitude": float, "longitude": float},
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
            "origin": data.get('origin'),
            "destination": data.get('destination'),
            "total_steps": data.get('total_steps'),
            "total_distance": data.get('total_distance'),
            "total_duration": data.get('total_duration'),
            "started_at": datetime.datetime.now().isoformat(),
            "completed_steps": 0,
            "status": "active"
        }
        
        print(f"🚀 Navigation started for session: {session_id}")
        print(f"📍 From: {data.get('origin')} To: {data.get('destination')}")
        print(f"📊 Total steps: {data.get('total_steps')}, Distance: {data.get('total_distance')}")
        
        return jsonify({
            "success": True,
            "message": "Navigation session started successfully",
            "session_id": session_id,
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error starting navigation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/step-completed', methods=['POST'])
def step_completed():
    """
    Receive step completion notification
    Expected data: {
        "session_id": "unique_session_id",
        "step_index": int,
        "step_instruction": "string",
        "step_distance": "string",
        "step_duration": "string",
        "current_location": {"latitude": float, "longitude": float},
        "completion_time": "ISO_datetime_string",
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
                "error": "Missing required fields: session_id, step_index, step_instruction, current_location"
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
            "step_duration": data.get('step_duration', 'N/A'),
            "current_location": current_location,
            "completion_time": data.get('completion_time', datetime.datetime.now().isoformat()),
            "accuracy": data.get('accuracy'),
            "server_timestamp": datetime.datetime.now().isoformat()
        }
        
        # Add to completed steps list
        completed_steps.append(step_completion)
        
        # Update session progress
        navigation_sessions[session_id]['completed_steps'] = step_index + 1
        navigation_sessions[session_id]['last_update'] = datetime.datetime.now().isoformat()
        
        # Log the completion
        print(f"✅ Step {step_index + 1} completed!")
        print(f"📋 Session: {session_id}")
        print(f"🗣️  Instruction: {step_instruction}")
        print(f"📍 Location: {current_location['latitude']:.6f}, {current_location['longitude']:.6f}")
        print(f"🎯 Accuracy: {data.get('accuracy', 'Unknown')}m")
        print(f"⏱️  Time: {step_completion['completion_time']}")
        print("=" * 60)
        
        # Calculate progress percentage
        total_steps = navigation_sessions[session_id].get('total_steps', 1)
        progress_percentage = ((step_index + 1) / total_steps) * 100
        
        return jsonify({
            "success": True,
            "message": f"Step {step_index + 1} completed successfully!",
            "step_index": step_index,
            "progress": {
                "completed_steps": step_index + 1,
                "total_steps": total_steps,
                "percentage": round(progress_percentage, 1)
            },
            "session_status": "active",
            "timestamp": datetime.datetime.now().isoformat(),
            "next_step_message": f"Great job! You've completed {step_index + 1} out of {total_steps} steps ({progress_percentage:.1f}% done)"
        }), 200
        
    except Exception as e:
        print(f"❌ Error processing step completion: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/complete', methods=['POST'])
def navigation_complete():
    """
    Mark navigation as completed
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
        if not session_id:
            return jsonify({
                "success": False,
                "error": "session_id is required"
            }), 400
        
        if session_id not in navigation_sessions:
            return jsonify({
                "success": False,
                "error": "Navigation session not found"
            }), 404
        
        # Update session as completed
        navigation_sessions[session_id]['status'] = 'completed'
        navigation_sessions[session_id]['completed_at'] = datetime.datetime.now().isoformat()
        navigation_sessions[session_id]['final_location'] = data.get('final_location')
        navigation_sessions[session_id]['actual_total_time'] = data.get('total_time')
        navigation_sessions[session_id]['actual_distance_traveled'] = data.get('total_distance_traveled')
        
        print(f"🎉 NAVIGATION COMPLETED!")
        print(f"📋 Session: {session_id}")
        print(f"📍 Final location: {data.get('final_location')}")
        print(f"⏱️  Total time: {data.get('total_time', 'N/A')}")
        print(f"🛣️  Distance traveled: {data.get('total_distance_traveled', 'N/A')}km")
        print("🎊 Congratulations on reaching your destination!")
        print("=" * 60)
        
        return jsonify({
            "success": True,
            "message": "🎉 Congratulations! Navigation completed successfully!",
            "session_summary": {
                "session_id": session_id,
                "total_steps_completed": navigation_sessions[session_id]['completed_steps'],
                "actual_time": data.get('total_time'),
                "actual_distance": data.get('total_distance_traveled'),
                "completed_at": navigation_sessions[session_id]['completed_at']
            },
            "timestamp": datetime.datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Error completing navigation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/status/<session_id>', methods=['GET'])
def get_navigation_status(session_id):
    """Get current navigation status and progress"""
    try:
        if session_id not in navigation_sessions:
            return jsonify({
                "success": False,
                "error": "Navigation session not found"
            }), 404
        
        session = navigation_sessions[session_id]
        
        # Get completed steps for this session
        session_steps = [step for step in completed_steps if step['session_id'] == session_id]
        
        return jsonify({
            "success": True,
            "session": session,
            "completed_steps_detail": session_steps,
            "summary": {
                "total_steps": session.get('total_steps', 0),
                "completed_steps": len(session_steps),
                "progress_percentage": (len(session_steps) / session.get('total_steps', 1)) * 100 if session.get('total_steps') else 0,
                "status": session.get('status', 'unknown')
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/navigation/sessions', methods=['GET'])
def get_all_sessions():
    """Get all navigation sessions"""
    try:
        return jsonify({
            "success": True,
            "sessions": list(navigation_sessions.values()),
            "total_sessions": len(navigation_sessions),
            "total_completed_steps": len(completed_steps)
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
        "active_sessions": len([s for s in navigation_sessions.values() if s.get('status') == 'active']),
        "total_sessions": len(navigation_sessions)
    }), 200

if __name__ == '__main__':
    print("🚀 Starting Navigation API Server...")
    print("📡 Listening for step completion notifications...")
    print("🔗 API Endpoints:")
    print("   POST /api/navigation/start - Start navigation session")
    print("   POST /api/navigation/step-completed - Step completion notification")
    print("   POST /api/navigation/complete - Mark navigation complete")
    print("   GET /api/navigation/status/<session_id> - Get session status")
    print("   GET /api/navigation/sessions - Get all sessions")
    print("   GET /api/health - Health check")
    print("=" * 60)
    
    # Run the server
    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=5000,       # Port 5000
        debug=True       # Enable debug mode
    )